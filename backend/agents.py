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


def scrape_page_metadata(
    url: str,
    timeout: float = 10.0,
    target_product_name: str | None = None,
) -> dict:
    """Scrape a page for product metadata via og: tags, twitter: tags, and JSON-LD.

    If target_product_name is set, only returns image/price when the page title
    matches the target product — prevents grabbing data from listing/category
    pages that show multiple products.
    """
    data: dict = {
        "image_url": None, "price": None, "title": None, "url": url,
        "is_single_product": False,
    }
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
            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            # -- Title --
            tag = soup.find("meta", property="og:title")
            if tag and tag.get("content"):
                data["title"] = tag["content"]
            elif soup.title and soup.title.string:
                data["title"] = soup.title.string.strip()

            # -- Detect listing / multi-product page --
            is_listing = _detect_listing_page(html, soup)
            if is_listing:
                data["is_single_product"] = False
                # On a listing page, only return canonical URL / title — not
                # image or price, because they belong to the page, not our product.
                canon = soup.find("link", rel="canonical")
                if canon and canon.get("href"):
                    data["url"] = canon["href"]
                return data

            # -- If target_product_name given, verify title matches --
            title_matches = True
            if target_product_name and data["title"]:
                title_matches = _product_name_matches_title(
                    target_product_name, data["title"]
                )

            data["is_single_product"] = True

            # -- Image (only if title matches) --
            if title_matches:
                for prop in ("og:image", "og:image:url"):
                    tag = soup.find("meta", property=prop)
                    if tag and tag.get("content", "").startswith("http"):
                        data["image_url"] = tag["content"]
                        break
                if not data["image_url"]:
                    tag = soup.find("meta", attrs={"name": "twitter:image"})
                    if tag and tag.get("content", "").startswith("http"):
                        data["image_url"] = tag["content"]

            # -- Price (meta, only if title matches) --
            if title_matches:
                for prop in ("og:price:amount", "product:price:amount"):
                    tag = soup.find("meta", property=prop)
                    if tag and tag.get("content"):
                        data["price"] = tag["content"]
                        break

            # -- Price (JSON-LD, with product-name guard) --
            if not data["price"]:
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld = json.loads(script.string or "")
                        if isinstance(ld, list):
                            ld = ld[0] if ld else {}
                        ld_type = str(ld.get("@type", "")).lower()
                        # Skip non-product schemas
                        if ld_type not in (
                            "product", "offer", "indivproduct",
                        ):
                            continue
                        # If we have a target name, verify JSON-LD name matches
                        ld_name = ld.get("name", "")
                        if target_product_name and ld_name:
                            if not _product_name_matches_title(
                                target_product_name, ld_name
                            ):
                                continue
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


def _detect_listing_page(html: str, soup) -> bool:
    """Detect whether an HTML page is a listing/category page with multiple products.

    Checks: multiple add-to-cart buttons, ItemList/CollectionPage JSON-LD,
    product-grid CSS patterns, and <h1> content.
    """
    html_lower = html.lower()

    # 1. Count "add to cart" / "buy now" occurrences — a product page has ~1,
    #    a listing page has many.
    atc_signals = [
        "add to cart", "add-to-cart", "addtocart",
        "add to bag", "add to basket",
    ]
    atc_count = sum(html_lower.count(s) for s in atc_signals)
    if atc_count > 3:
        return True

    # 2. JSON-LD types that mean "listing" not "single product"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string or "")
            if isinstance(ld, list):
                # Multiple Product objects in one JSON-LD block → listing
                product_count = sum(
                    1 for item in ld
                    if isinstance(item, dict)
                    and str(item.get("@type", "")).lower() == "product"
                )
                if product_count > 1:
                    return True
                ld = ld[0] if ld else {}
            ld_type = str(ld.get("@type", "")).lower()
            if ld_type in (
                "itemlist", "collectionpage", "searchresultspage",
                "offerlist", "breadcrumblist",
            ):
                # BreadcrumbList alone is fine on product pages — only flag if
                # it's the ONLY LD+JSON block (no Product block found)
                if ld_type != "breadcrumblist":
                    return True
            # Check for itemListElement with many entries
            items = ld.get("itemListElement", [])
            if isinstance(items, list) and len(items) > 3:
                return True
        except Exception:
            continue

    # 3. CSS class patterns typical of product grids
    grid_patterns = [
        'class="product-grid', 'class="product-list',
        'class="products-grid', 'class="products-list',
        'class="search-results', 'class="collection-products',
        'data-product-grid', 'product-card',
    ]
    grid_hits = sum(1 for p in grid_patterns if p in html_lower)
    if grid_hits >= 2:
        return True

    # 4. Count separate product-card-like elements
    product_cards = soup.find_all(
        class_=re.compile(
            r"product[-_]?card|product[-_]?tile|product[-_]?item",
            re.IGNORECASE,
        )
    )
    if len(product_cards) > 2:
        return True

    return False


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
    """Validates primary agent picks and gathers product details.

    This agent focuses ONLY on product quality information (features,
    pros, cons, rating, why_to_buy).  It does NOT handle URLs or images —
    those are the responsibility of PriceComparisonAgent.

    Workflow per product:
      1. Targeted Tavily search (reviews / specs)
      2. LLM analyses collected text → structured quality fields
      3. Returns validation verdict + detail fields
    """

    def __init__(self):
        self.llm = default_llm

    def gather_details(self, product_name: str) -> dict:
        # -- 1. Targeted search for reviews & specs --
        search_data = tavily_search(
            query=f"{product_name} detailed review specs features pros cons",
            max_results=5,
            search_depth="advanced",
        )
        results = search_data.get("results", [])

        # -- 2. Build context text --
        content_parts = []
        for r in results:
            content_parts.append(
                f"Source: {r.get('url', '')}\n{r.get('content', '')}"
            )
        content_text = "\n\n---\n\n".join(content_parts)[:5000]

        # -- 3. LLM analysis (no URLs, no images) --
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Product Analyst that validates product picks.\n"
                    "Analyse the search content and return a JSON object with these EXACT fields:\n"
                    "{{\n"
                    '  "name": "Full product name (corrected if needed)",\n'
                    '  "approximate_price": "numeric string e.g. 299.99 or null if unknown",\n'
                    '  "rating": 4.5,\n'
                    '  "reviews_count": 1234,\n'
                    '  "features": ["feature 1", "feature 2"],\n'
                    '  "pros": ["pro 1", "pro 2", "pro 3"],\n'
                    '  "cons": ["con 1", "con 2"],\n'
                    '  "why_to_buy": "1-2 sentence compelling reason",\n'
                    '  "is_valid_product": true\n'
                    "}}\n\n"
                    "RULES:\n"
                    "- rating MUST be a float 1.0-5.0.\n"
                    "- 3-5 features, 3-4 pros, 2-3 cons.\n"
                    "- is_valid_product = false if the product doesn't seem to exist "
                    "or search results are irrelevant.\n"
                    "- Do NOT generate URLs or image links.\n"
                    "- No <think> tags, no markdown fences, ONLY the JSON object.",
                ),
                (
                    "user",
                    "Product to validate: {product_name}\n\n"
                    "Search Content:\n{content}",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        analysis = parse_json_output(
            chain.invoke(
                {
                    "product_name": product_name,
                    "content": content_text,
                }
            )
        )
        if not isinstance(analysis, dict):
            analysis = {}

        return {
            "name": analysis.get("name", product_name),
            "approximate_price": analysis.get("approximate_price"),
            "rating": analysis.get("rating", 4.0),
            "reviews_count": analysis.get("reviews_count"),
            "features": analysis.get("features", []),
            "pros": analysis.get("pros", []),
            "cons": analysis.get("cons", []),
            "why_to_buy": analysis.get("why_to_buy", ""),
            "is_valid_product": analysis.get("is_valid_product", True),
        }


# ---------------------------------------------------------------------------
# Price Comparison Agent (URLs from search results, never hallucinated)
# ---------------------------------------------------------------------------


class PriceComparisonAgent:
    """Finds best prices across retailers AND provides the primary buy links/images.

    This is the single source of truth for:
      - product URL (direct buy link)
      - product image (scraped from retailer page)
      - price (scraped from retailer page)
      - price_comparison list
      - cheapest_link

    Workflow:
      1. Search Tavily for "{product_name}" buy price across retailers
      2. LLM identifies retailers + prices from search results
      3. Scrape top retailer pages → extract image, price, canonical URL
      4. Return all data including the best buy URL and image
    """

    def __init__(self):
        self.llm = default_llm

    def compare_prices(self, product_name: str, approximate_price: str | None = None) -> dict:
        # -- 1. Search for buy links --
        search_data = tavily_search(
            query=f'"{product_name}" buy price',
            max_results=5,
            search_depth="advanced",
            include_images=True,
        )
        results = search_data.get("results", [])
        search_images = search_data.get("images", [])

        # Also do a targeted retailer search
        retailer_search = tavily_search(
            query=f"{product_name} buy site:amazon.com OR site:walmart.com OR site:bestbuy.com OR site:target.com",
            max_results=5,
            search_depth="basic",
            include_images=True,
        )
        retailer_results = retailer_search.get("results", [])
        retailer_images = retailer_search.get("images", [])

        # Merge results (dedup by URL)
        seen_urls: set[str] = set()
        all_results = []
        for r in results + retailer_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
        all_images = search_images + retailer_images

        # -- 2. Number results for LLM --
        url_map: dict[int, str] = {}
        numbered: list[str] = []
        for i, r in enumerate(all_results):
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
                    "1. Reference results by index [0]-[{max_idx}].\n"
                    "2. Extract REAL prices from the snippets - never invent prices.\n"
                    "3. Identify retailer from the URL domain "
                    "(amazon.com -> Amazon, bestbuy.com -> Best Buy, etc.).\n"
                    "4. ONLY include results that are direct product/buy pages "
                    "(NOT reviews, articles, blogs, or comparison pages).\n"
                    "5. Return ONLY JSON - no <think> tags, no markdown fences.\n\n"
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
                    "max_idx": len(all_results) - 1,
                }
            )
        )
        if not isinstance(raw, dict):
            raw = {}

        # -- 3. Map indices to real URLs and build comparison list --
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

        # -- 4. Scrape top retailer pages for image, price, canonical URL --
        # Prioritise the best_source_index, then others
        best_idx = raw.get("best_source_index")
        scrape_order: list[int] = []
        if isinstance(best_idx, int) and best_idx in url_map:
            scrape_order.append(best_idx)
        for item in raw.get("retailers", []):
            if isinstance(item, dict):
                idx = item.get("source_index", -1)
                if idx in url_map and idx not in scrape_order:
                    scrape_order.append(idx)
        # Also add any remaining result URLs that look like retailer pages
        for i, url in url_map.items():
            if i not in scrape_order and any(d in url for d in _RETAILER_DOMAINS):
                scrape_order.append(i)

        best_buy_url: str = ""
        best_image_url: Optional[str] = None
        best_scraped_price: Optional[str] = None
        scraped_seen: set[str] = set()

        for idx in scrape_order[:5]:
            url = url_map.get(idx, "")
            if not url or url in scraped_seen:
                continue
            scraped_seen.add(url)

            # Skip URLs that look like listing/category pages
            if _LISTING_URL_PATTERNS.search(url):
                print(f"[price-comp] Skipping listing URL: {url}")
                continue

            meta = scrape_page_metadata(url, target_product_name=product_name)

            # Only accept data from single-product pages
            if not meta.get("is_single_product", False):
                print(f"[price-comp] Skipping non-product page: {url}")
                continue

            # Verify title matches our product before trusting image/price
            title_matches = _product_name_matches_title(
                product_name, meta.get("title")
            )

            if not best_buy_url:
                best_buy_url = meta.get("url") or url

            if not best_image_url and meta.get("image_url") and title_matches:
                best_image_url = meta["image_url"]

            if not best_scraped_price and meta.get("price") and title_matches:
                best_scraped_price = meta["price"]

            # If we have all three, stop scraping
            if best_buy_url and best_image_url and best_scraped_price:
                break

        # -- 5. Fallback image search if scraping found nothing --
        # Use exact product name to avoid getting a generic category image
        if not best_image_url:
            best_image_url = find_product_image(product_name)
        # NOTE: Do NOT fall back to all_images (Tavily search images) — those
        # are often article hero images or thumbnails from listing pages,
        # not images of our specific product.

        # -- 6. Determine cheapest link --
        cheapest_link = ""
        if isinstance(best_idx, int) and best_idx in url_map:
            cheapest_link = url_map[best_idx]
        if not cheapest_link and price_comparison:
            min_price = float("inf")
            for pc in price_comparison:
                try:
                    p = float(str(pc["price"]).replace("$", "").replace(",", ""))
                    if p < min_price:
                        min_price = p
                        cheapest_link = pc["url"]
                except (ValueError, TypeError):
                    pass
        if not cheapest_link:
            cheapest_link = best_buy_url

        # -- 7. Determine best price --
        final_price = best_scraped_price or raw.get("best_price") or approximate_price
        if not final_price and price_comparison:
            prices_found: list[float] = []
            for rp in price_comparison:
                pv = rp.get("price", "")
                try:
                    prices_found.append(
                        float(str(pv).replace("$", "").replace(",", ""))
                    )
                except (ValueError, TypeError):
                    pass
            if prices_found:
                final_price = f"${min(prices_found):.2f}"

        return {
            "price_comparison": price_comparison,
            "cheapest_link": cheapest_link,
            "best_price": raw.get("best_price"),
            "price": final_price or "Price not available",
            "url": best_buy_url,
            "image_url": best_image_url,
        }


# ---------------------------------------------------------------------------
# Recommendation Agent
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Link Verification Agent
# ---------------------------------------------------------------------------

# URL patterns that are almost certainly NOT direct-buy product pages
_GENERIC_URL_PATTERNS = re.compile(
    r"(/search[/?]|/category/|/categories/|/collections?/"
    r"|/blog/|/article/|/news/|/review/|/best-|/top-\d"
    r"|/comparison|/vs[/-]|/guide|/wiki/|/tag/|/tags/"
    r"|reddit\.com|youtube\.com|quora\.com|medium\.com"
    r"|/shop/?$|/shop/?\?|/products/?$|/products/?\?"
    r"|/all-products|/catalog/?$)",
    re.IGNORECASE,
)

# URL patterns that signal a LISTING / CATEGORY / MULTI-PRODUCT page
_LISTING_URL_PATTERNS = re.compile(
    r"(/shop/?$|/shop/?\?|/shop/[a-z-]+/?$"
    r"|/products/?$|/products/?\?|/products/[a-z-]+/?$"
    r"|/category/|/categories/|/collections?/"
    r"|/all-products|/catalog"
    r"|/search[/?]|[?&]q=|[?&]query="
    r"|/browse/|/listing)",
    re.IGNORECASE,
)

# URL patterns that signal a direct product page on known retailers
# These are SPECIFIC patterns (with IDs/SKUs), not generic /product/ paths
_PRODUCT_URL_PATTERNS = re.compile(
    r"(/dp/[A-Z0-9]{10}|/gp/product/[A-Z0-9]"          # Amazon
    r"|walmart\.com/ip/"                                  # Walmart /ip/<slug>/<id>
    r"|bestbuy\.com/site/.+/\d{7}\.p"                    # Best Buy
    r"|newegg\.com/.+?/p/"                               # Newegg
    r"|bhphotovideo\.com/c/product/"                      # B&H
    r"|adorama\.com/.*/\d+\.html"                         # Adorama
    r"|target\.com/p/.+/-/A-\d"                           # Target
    r"|/product/[A-Za-z0-9_-]{4,}"                       # generic /product/<id>
    r"|/item/[A-Za-z0-9_-]{4,}"                          # generic /item/<id>
    r"|ebay\.com/itm/\d)",                                # eBay
    re.IGNORECASE,
)

# Major retailers where we'd want to find buy links
_RETAILER_DOMAINS = [
    "amazon.com", "walmart.com", "bestbuy.com", "target.com",
    "newegg.com", "bhphotovideo.com", "adorama.com", "ebay.com",
    "costco.com", "homedepot.com", "lowes.com",
]


def _is_product_page_by_url(url: str) -> bool:
    """Heuristic: does the URL structure look like a product page?"""
    if not url:
        return False
    if _LISTING_URL_PATTERNS.search(url):
        return False
    if _GENERIC_URL_PATTERNS.search(url):
        return False
    if _PRODUCT_URL_PATTERNS.search(url):
        return True
    return False  # ambiguous – will need scraping to verify


def _product_name_matches_title(product_name: str, page_title: str | None) -> bool:
    """Check if significant words from product_name appear in page_title."""
    if not page_title or not product_name:
        return False
    # Extract significant words (>2 chars, not common filler)
    filler = {"the", "and", "for", "with", "new", "best", "buy", "sale", "price"}
    name_words = [
        w.lower()
        for w in re.findall(r"\w+", product_name)
        if len(w) > 2 and w.lower() not in filler
    ]
    if not name_words:
        return False
    title_lower = page_title.lower()
    matched = sum(1 for w in name_words if w in title_lower)
    # Require at least 50% of significant words to match, minimum 2
    threshold = max(2, len(name_words) * 0.5)
    return matched >= threshold


def _extract_price_float(price_str) -> float | None:
    """Parse a price string into a float, returns None on failure."""
    if price_str is None:
        return None
    s = str(price_str).replace("$", "").replace(",", "").strip()
    match = re.search(r"(\d+\.?\d*)", s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def _prices_match(price_a, price_b, tolerance: float = 0.15) -> bool:
    """Check if two prices are within tolerance (default 15%) of each other."""
    a = _extract_price_float(price_a)
    b = _extract_price_float(price_b)
    if a is None or b is None:
        return True  # can't verify → don't flag
    if a == 0 and b == 0:
        return True
    avg = (a + b) / 2.0
    if avg == 0:
        return True
    return abs(a - b) / avg <= tolerance


class LinkVerificationAgent:
    """Verifies product buy-links are real, direct purchase pages.

    For each product it:
      1. Analyses the URL structure (known retailer patterns)
      2. Scrapes the page for product signals (og:type, JSON-LD Product,
         add-to-cart indicators, product name presence)
      3. Optionally checks price consistency
      4. If the link fails verification → searches for a correct buy link
      5. Verifies the replacement link too before accepting it
    """

    def __init__(self):
        self.llm = default_llm

    # ----- scrape-based verification ------------------------------------

    def _scrape_verify(self, url: str, product_name: str) -> dict:
        """Scrape a URL and return verification signals.

        Key improvement: detects listing/category pages (multiple products)
        and rejects them even if they contain buy buttons and product names.

        Returns dict with keys:
          is_product_page (bool), is_listing_page (bool),
          page_title (str|None), page_price (str|None), page_image (str|None),
          has_buy_button (bool), has_single_buy_button (bool),
          has_product_schema (bool), name_matches (bool)
        """
        result = {
            "is_product_page": False,
            "is_listing_page": False,
            "page_title": None,
            "page_price": None,
            "page_image": None,
            "has_buy_button": False,
            "has_single_buy_button": False,
            "has_product_schema": False,
            "name_matches": False,
        }

        if not url or not url.startswith("http"):
            return result

        # Quick URL-level rejection for listing pages
        if _LISTING_URL_PATTERNS.search(url):
            result["is_listing_page"] = True
            return result

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            result["is_product_page"] = _is_product_page_by_url(url)
            return result

        try:
            with httpx.Client(
                follow_redirects=True, timeout=12.0, headers=_SCRAPER_HEADERS
            ) as client:
                resp = client.get(url)
                if resp.status_code >= 400:
                    return result
                html = resp.text
                soup = BeautifulSoup(html, "lxml")

                # --- Check if this is a listing page FIRST ---
                if _detect_listing_page(html, soup):
                    result["is_listing_page"] = True
                    # Still extract title for logging
                    tag = soup.find("meta", property="og:title")
                    if tag and tag.get("content"):
                        result["page_title"] = tag["content"]
                    elif soup.title and soup.title.string:
                        result["page_title"] = soup.title.string.strip()
                    return result

                # --- Title ---
                tag = soup.find("meta", property="og:title")
                if tag and tag.get("content"):
                    result["page_title"] = tag["content"]
                elif soup.title and soup.title.string:
                    result["page_title"] = soup.title.string.strip()

                # --- Image (og:image) ---
                for prop in ("og:image", "og:image:url"):
                    tag = soup.find("meta", property=prop)
                    if tag and tag.get("content", "").startswith("http"):
                        result["page_image"] = tag["content"]
                        break
                if not result["page_image"]:
                    tag = soup.find("meta", attrs={"name": "twitter:image"})
                    if tag and tag.get("content", "").startswith("http"):
                        result["page_image"] = tag["content"]

                # --- og:type == product ---
                og_type = soup.find("meta", property="og:type")
                if og_type and "product" in (og_type.get("content") or "").lower():
                    result["has_product_schema"] = True

                # --- JSON-LD Product schema ---
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld = json.loads(script.string or "")
                        if isinstance(ld, list):
                            ld = ld[0] if ld else {}
                        ld_type = str(ld.get("@type", "")).lower()
                        if ld_type in ("product", "offer", "indivproduct"):
                            result["has_product_schema"] = True
                            offers = ld.get("offers", ld.get("Offers", {}))
                            if isinstance(offers, list):
                                offers = offers[0] if offers else {}
                            if isinstance(offers, dict):
                                pv = offers.get("price") or offers.get("lowPrice")
                                if pv:
                                    result["page_price"] = str(pv)
                            break
                    except Exception:
                        continue

                # --- Price from meta ---
                if not result["page_price"]:
                    for prop in ("og:price:amount", "product:price:amount"):
                        tag = soup.find("meta", property=prop)
                        if tag and tag.get("content"):
                            result["page_price"] = tag["content"]
                            break

                # --- Buy / Add-to-cart button (count-aware) ---
                html_lower = html.lower()
                atc_signals = [
                    "add to cart", "add-to-cart", "addtocart",
                    "buy now", "buy-now", "buynow",
                    "add to bag", "add to basket",
                ]
                atc_count = sum(html_lower.count(s) for s in atc_signals)
                result["has_buy_button"] = atc_count > 0
                # A real product page typically has 1-2 buy buttons
                # (e.g. sticky header + main). More than 3 is suspicious.
                result["has_single_buy_button"] = 0 < atc_count <= 3

                # --- Name match (strict: use title, not body text) ---
                result["name_matches"] = _product_name_matches_title(
                    product_name, result["page_title"]
                )

                # --- Final decision ---
                # A real product page needs: name matches + (product schema OR
                # single buy button). Listing pages get caught by the
                # _detect_listing_page check above, but we add extra safety here:
                # even if not detected as listing, require name match to be strict.
                if result["name_matches"]:
                    if result["has_product_schema"] and result["has_single_buy_button"]:
                        result["is_product_page"] = True
                    elif result["has_product_schema"]:
                        result["is_product_page"] = True
                    elif result["has_single_buy_button"]:
                        result["is_product_page"] = True
                # Without name match, only pass if we have both schema + buy button
                elif result["has_product_schema"] and result["has_single_buy_button"]:
                    result["is_product_page"] = True

                # Guard: if image/price came from a page where name doesn't match,
                # clear them to avoid using wrong product's data
                if not result["name_matches"]:
                    result["page_image"] = None
                    result["page_price"] = None

        except Exception as e:
            print(f"[link-verify-scrape] {url}: {e}")

        return result

    # ----- search for correct buy link ----------------------------------

    def _search_buy_links(self, product_name: str) -> list[dict]:
        """Search for direct buy links on major retailers.

        Returns list of {url, retailer, price} dicts.
        """
        candidates: list[dict] = []

        # Strategy 1: targeted retailer searches via Tavily
        queries = [
            f'"{product_name}" buy site:amazon.com OR site:walmart.com OR site:bestbuy.com',
            f'"{product_name}" buy price',
        ]

        seen_urls: set[str] = set()
        for q in queries:
            search_data = tavily_search(
                query=q, max_results=5, search_depth="basic"
            )
            for r in search_data.get("results", []):
                url = r.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append({
                    "url": url,
                    "title": r.get("title", ""),
                    "snippet": r.get("content", "")[:400],
                })

        return candidates

    def _find_best_buy_link(
        self, product_name: str, expected_price=None
    ) -> dict | None:
        """Search and verify to find the best direct buy link.

        Returns {url, retailer, price} or None.
        """
        candidates = self._search_buy_links(product_name)

        # Score and sort candidates
        scored: list[tuple[float, dict]] = []
        for c in candidates:
            url = c["url"]
            score = 0.0

            # Prefer known retailer domains
            for domain in _RETAILER_DOMAINS:
                if domain in url:
                    score += 3.0
                    break

            # Prefer product URL patterns
            if _PRODUCT_URL_PATTERNS.search(url):
                score += 4.0

            # Penalise generic URL patterns
            if _GENERIC_URL_PATTERNS.search(url):
                score -= 5.0

            # Check product name words in title
            name_words = set(
                w.lower() for w in re.findall(r"\w+", product_name) if len(w) > 2
            )
            title_lower = c.get("title", "").lower()
            matched = sum(1 for w in name_words if w in title_lower)
            score += matched * 0.5

            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Verify top candidates (max 3) by scraping
        for _score, c in scored[:3]:
            url = c["url"]
            verify = self._scrape_verify(url, product_name)
            if verify["is_product_page"] or (
                verify["name_matches"] and verify["has_buy_button"]
            ):
                # Determine retailer from domain
                retailer = "Unknown"
                for domain in _RETAILER_DOMAINS:
                    if domain in url:
                        retailer = domain.split(".")[0].capitalize()
                        break

                page_price = verify.get("page_price")
                if expected_price and page_price and not _prices_match(
                    expected_price, page_price, tolerance=0.25
                ):
                    # Price mismatch is suspicious – might be wrong product
                    continue

                return {
                    "url": url,
                    "retailer": retailer,
                    "price": page_price,
                }

        # If no verified candidate, return best-scored known retailer link
        for _score, c in scored[:5]:
            url = c["url"]
            if any(domain in url for domain in _RETAILER_DOMAINS):
                if not _GENERIC_URL_PATTERNS.search(url):
                    retailer = "Unknown"
                    for domain in _RETAILER_DOMAINS:
                        if domain in url:
                            retailer = domain.split(".")[0].capitalize()
                            break
                    return {"url": url, "retailer": retailer, "price": None}

        return None

    # ----- LLM-assisted URL classification (fallback) -------------------

    def _llm_classify_url(self, url: str, page_title: str | None, product_name: str) -> bool:
        """Use LLM as fallback to decide if a URL is a direct product page."""
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You determine whether a URL is a DIRECT PRODUCT PURCHASE PAGE "
                    "(where a customer can buy a specific product) versus a review, "
                    "article, category listing, search results page, or other non-purchase page.\n\n"
                    "Reply with ONLY 'YES' or 'NO'. No explanation.",
                ),
                (
                    "user",
                    "Product: {product_name}\n"
                    "URL: {url}\n"
                    "Page Title: {page_title}\n\n"
                    "Is this a direct product purchase page?",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            answer = chain.invoke({
                "product_name": product_name,
                "url": url,
                "page_title": page_title or "Unknown",
            }).strip().upper()
            return answer.startswith("YES")
        except Exception as e:
            print(f"[link-verify-llm] {url}: {e}")
            return False

    # ----- Main entry point ---------------------------------------------

    def verify_product_links(self, product: dict) -> dict:
        """Verify and fix all links for a single product.

        Mutates and returns the product dict with corrected URLs.
        Also updates image_url and price from verified pages when better data is found.
        Adds a 'link_verified' boolean field.
        """
        product_name = product.get("name", "Unknown")
        expected_price = product.get("price")
        main_url = product.get("url", "")
        cheapest_link = product.get("cheapest_link", "")

        def _update_from_verification(v: dict) -> None:
            """Update product price/image from scrape verification data."""
            if v.get("page_price") and product.get("price") in (
                "Price not available", "Price varies", None, "",
            ):
                product["price"] = v["page_price"]
            if v.get("page_image") and not product.get("image_url"):
                product["image_url"] = v["page_image"]

        # --- Verify main URL ---
        main_verified = False
        if main_url:
            v = self._scrape_verify(main_url, product_name)
            main_verified = v["is_product_page"]
            if not main_verified and v.get("page_title"):
                # LLM fallback for ambiguous cases
                main_verified = self._llm_classify_url(
                    main_url, v["page_title"], product_name
                )
            if main_verified:
                _update_from_verification(v)

        # --- Verify cheapest_link (if different from main) ---
        cheapest_verified = False
        if cheapest_link and cheapest_link != main_url:
            v2 = self._scrape_verify(cheapest_link, product_name)
            cheapest_verified = v2["is_product_page"]
            if not cheapest_verified and v2.get("page_title"):
                cheapest_verified = self._llm_classify_url(
                    cheapest_link, v2["page_title"], product_name
                )
            if cheapest_verified:
                _update_from_verification(v2)
        elif cheapest_link == main_url:
            cheapest_verified = main_verified

        # --- Verify price_comparison links ---
        verified_comparisons: list[dict] = []
        for pc in product.get("price_comparison", []):
            pc_url = pc.get("url", "")
            if not pc_url:
                continue
            if _GENERIC_URL_PATTERNS.search(pc_url):
                continue  # drop clearly generic links
            if _is_product_page_by_url(pc_url):
                verified_comparisons.append(pc)
            else:
                # Light scrape check (no LLM for individual comparison links)
                v3 = self._scrape_verify(pc_url, product_name)
                if v3["is_product_page"] or v3["name_matches"]:
                    verified_comparisons.append(pc)
        product["price_comparison"] = verified_comparisons

        # --- If main URL failed verification, find a replacement ---
        if not main_verified:
            print(f"[link-verify] Main URL failed for '{product_name}': {main_url}")
            replacement = self._find_best_buy_link(product_name, expected_price)
            if replacement:
                product["url"] = replacement["url"]
                main_verified = True
                print(f"[link-verify] Replaced with: {replacement['url']}")
                if replacement.get("price") and product.get("price") in (
                    "Price not available", "Price varies", None, "",
                ):
                    product["price"] = replacement["price"]
                # Scrape the replacement for image if we still don't have one
                if not product.get("image_url"):
                    rv = self._scrape_verify(replacement["url"], product_name)
                    if rv.get("page_image"):
                        product["image_url"] = rv["page_image"]
            else:
                print(f"[link-verify] No replacement found for '{product_name}'")

        # --- If cheapest_link failed, use main URL or find new ---
        if not cheapest_verified:
            if main_verified:
                product["cheapest_link"] = product["url"]
            else:
                # Try to pick from verified comparison links
                if verified_comparisons:
                    best_pc = None
                    best_price = float("inf")
                    for pc in verified_comparisons:
                        p = _extract_price_float(pc.get("price"))
                        if p is not None and p < best_price:
                            best_price = p
                            best_pc = pc
                    if best_pc:
                        product["cheapest_link"] = best_pc["url"]

        product["link_verified"] = main_verified
        return product


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
