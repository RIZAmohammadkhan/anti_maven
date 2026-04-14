"""
Scorer CLI — scores collected Maven responses against the gold sheet.

Usage:
    python -m evaluation.score --run evaluation/runs/baseline --gold evaluation/gold.jsonl

Scoring:
    Product-level (out of 100):
        25 — relevance/existence
        20 — budget & price fit
        20 — feature match
        20 — link integrity
        15 — evidence completeness

    Query-level (out of 100):
        0.70 * mean(product_scores)
        0.20 * recommendation_alignment
        0.10 * response_integrity
"""

import argparse
import json
import pathlib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_price(price_val) -> float | None:
    """Parse a price value to float, returning None on failure."""
    if price_val is None:
        return None
    s = str(price_val).strip()
    if not s or s.lower() in ("null", "none", "n/a", "price not available", "price varies", "0", "0.0", "0.00"):
        return None
    s = s.replace("$", "").replace(",", "").replace("₹", "").strip()
    m = re.search(r"(\d+\.?\d*)", s)
    if m:
        val = float(m.group(1))
        return val if val > 0 else None
    return None


# Synonyms: if a gold feature says X, also accept Y in product text
_FEATURE_SYNONYMS: dict[str, list[str]] = {
    "wireless": ["bluetooth", "bt", "true wireless", "tws"],
    "bluetooth": ["wireless", "bt"],
    "noise cancelling": ["anc", "active noise", "noise cancellation", "noise-cancelling"],
    "waterproof": ["water resistant", "water-resistant", "ipx7", "ipx8", "ip67", "ip68"],
    "water resistant": ["waterproof", "ipx", "ip6"],
    "usb-c": ["type-c", "usb c", "type c"],
    "fast charging": ["quick charge", "rapid charge", "turbo charge", "67w", "65w", "45w"],
    "long battery": ["battery life", "hour battery", "all-day"],
    "lightweight": ["light weight", "ultra-light", "ultralight"],
    "ergonomic": ["ergonomically designed", "ergonomical"],
    "mechanical": ["mech", "mechanical switch"],
    "dedicated gpu": ["discrete gpu", "rtx", "geforce", "radeon"],
    "good camera": ["camera", "megapixel", "photo", "photography"],
    "adjustable lumbar": ["lumbar", "lumbar support"],
    "self-emptying": ["auto-empty", "auto empty", "self empty"],
    "quiet operation": ["quiet", "low noise", "silent", "whisper"],
    "pet hair friendly": ["pet hair", "pet", "pets"],
    "suitable for running": ["running", "jogging", "sport", "workout"],
    "suitable for gaming": ["gaming", "game", "gamer"],
    "suitable for students": ["student", "school", "college", "study"],
    "suitable for beginners": ["beginner", "entry-level", "starter", "getting started"],
    "suitable for travel": ["travel", "portable", "compact", "on-the-go"],
    "suitable for home use": ["home", "household"],
    "suitable for commuting": ["commute", "commuting", "travel"],
    "suitable for programming": ["programming", "coding", "developer", "development"],
    "suitable for video editing": ["video editing", "video production", "premiere", "davinci"],
    "suitable for office": ["office", "work", "professional"],
    "suitable for gym": ["gym", "workout", "exercise", "fitness"],
    "suitable for apartments": ["apartment", "small space", "compact"],
    "suitable for kids": ["kids", "children", "child"],
    "suitable for seniors": ["seniors", "elderly", "easy to use", "simple"],
    "suitable for streaming": ["streaming", "stream", "twitch", "obs"],
    "suitable for camping": ["camping", "outdoor", "outdoors"],
    "suitable for vlogging": ["vlogging", "vlog", "video"],
    "suitable for photo editing": ["photo editing", "lightroom", "photoshop"],
    "suitable for coding": ["coding", "code", "programming", "developer"],
    "compact size": ["compact", "small", "mini", "portable"],
}


def _text_contains_feature(text: str, feature: str) -> bool:
    """Case-insensitive check if text contains a feature keyword."""
    if not text or not feature:
        return False
    # Normalize both
    text_lower = text.lower()
    feature_lower = feature.lower()

    # Direct containment
    if feature_lower in text_lower:
        return True

    # Check synonyms
    synonyms = _FEATURE_SYNONYMS.get(feature_lower, [])
    for syn in synonyms:
        if syn in text_lower:
            return True

    # Check individual words (for multi-word features, require all significant words)
    feature_words = [w for w in re.findall(r"\w+", feature_lower) if len(w) > 2]
    if not feature_words:
        return feature_lower in text_lower

    matched = sum(1 for w in feature_words if w in text_lower)
    if matched >= len(feature_words) * 0.7:
        return True

    # Try synonym words too
    for syn in synonyms:
        syn_words = [w for w in re.findall(r"\w+", syn) if len(w) > 2]
        if syn_words:
            syn_matched = sum(1 for w in syn_words if w in text_lower)
            if syn_matched >= len(syn_words) * 0.7:
                return True

    return False


def _check_url_reachable(url: str, timeout: float = 10.0) -> dict:
    """Check if a URL is reachable and looks like a product page.

    Returns {reachable, is_product_page, status_code, reason}.
    """
    result = {
        "reachable": False,
        "is_product_page": False,
        "status_code": None,
        "reason": "not checked",
    }

    if not url or not url.startswith("http"):
        result["reason"] = "invalid URL"
        return result

    # URL-level rejection patterns
    non_product_patterns = re.compile(
        r"(/search[/?]|/category/|/categories/|/collections?/"
        r"|/blog/|/article/|/news/|/review/|/best-|/top-\d"
        r"|/comparison|/vs[/-]|/guide|/wiki/"
        r"|reddit\.com|youtube\.com|quora\.com|medium\.com"
        r"|/shop/?$|/shop/?\?|/products/?$|/products/?\?"
        r"|/all-products|/catalog/?$"
        r"|/browse/|/listing)",
        re.IGNORECASE,
    )

    product_patterns = re.compile(
        r"(/dp/[A-Z0-9]{10}|/gp/product/"
        r"|walmart\.com/ip/"
        r"|bestbuy\.com/site/.+/\d{7}\.p"
        r"|target\.com/p/.+/-/A-\d"
        r"|/product/[A-Za-z0-9_-]{4,}"
        r"|/item/[A-Za-z0-9_-]{4,}"
        r"|ebay\.com/itm/\d)",
        re.IGNORECASE,
    )

    if non_product_patterns.search(url):
        result["reason"] = "URL pattern matches review/listing/generic page"
        # Still check reachability
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.head(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; MavenEval/1.0)"
                })
                result["reachable"] = resp.status_code < 400
                result["status_code"] = resp.status_code
        except Exception:
            pass
        return result

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; MavenEval/1.0)"
            })
            result["status_code"] = resp.status_code
            result["reachable"] = resp.status_code < 400

            if result["reachable"]:
                # Check if URL looks like a product page
                if product_patterns.search(url):
                    result["is_product_page"] = True
                    result["reason"] = "reachable, matches product URL pattern"
                else:
                    # Ambiguous URL — give partial credit
                    result["is_product_page"] = True  # benefit of the doubt
                    result["reason"] = "reachable, ambiguous URL pattern"
            else:
                result["reason"] = f"HTTP {resp.status_code}"

    except httpx.TimeoutException:
        result["reason"] = "timeout"
    except Exception as e:
        result["reason"] = f"{type(e).__name__}: {str(e)[:100]}"

    return result


# ---------------------------------------------------------------------------
# Product-level scoring
# ---------------------------------------------------------------------------

def score_product(product: dict, gold: dict, link_checks: dict) -> dict:
    """Score a single product against gold constraints.

    Returns dict with total score and component breakdowns.
    """
    scores = {
        "relevance": 0.0,
        "budget_price": 0.0,
        "feature_match": 0.0,
        "link_integrity": 0.0,
        "evidence_completeness": 0.0,
        "total": 0.0,
        "details": {},
    }

    product_name = str(product.get("name", "")).lower()
    product_features = " ".join(str(f) for f in product.get("features", []))
    product_pros = " ".join(str(p) for p in product.get("pros", []))
    product_why = str(product.get("why_to_buy", ""))
    product_text = f"{product_name} {product_features} {product_pros} {product_why}".lower()

    # --- 1. Relevance / Existence (25 points) ---
    gold_product_type = gold.get("product_type", "").lower()
    must_not_have = [t.lower() for t in gold.get("must_not_have_terms", [])]
    anchor_products = [a.lower() for a in gold.get("anchor_products", [])]

    relevance = 25.0

    # First check: is this product one of the known anchor products?
    is_anchor = False
    if anchor_products:
        for anchor in anchor_products:
            anchor_words = [w for w in re.findall(r"\w+", anchor) if len(w) > 2]
            if anchor_words:
                anchor_match = sum(1 for w in anchor_words if w in product_name) / len(anchor_words)
                if anchor_match >= 0.5:
                    is_anchor = True
                    break

    if is_anchor:
        relevance = 25.0  # Anchor product gets full relevance
    else:
        # Check if product type words appear in product name/features
        type_words = [w for w in re.findall(r"\w+", gold_product_type) if len(w) > 2]
        if type_words:
            type_match = sum(1 for w in type_words if w in product_text) / len(type_words)
            if type_match < 0.3:
                relevance = 5.0  # Very low relevance
                scores["details"]["relevance_issue"] = f"product type '{gold_product_type}' poorly matched"
            elif type_match < 0.6:
                relevance = 15.0
                scores["details"]["relevance_issue"] = f"product type '{gold_product_type}' partially matched"

    # Check must_not_have terms
    for term in must_not_have:
        if term in product_text:
            relevance = max(0, relevance - 10)
            scores["details"].setdefault("must_not_have_violations", []).append(term)

    scores["relevance"] = relevance

    # --- 2. Budget & Price Fit (20 points) ---
    budget_score = 20.0
    price = _parse_price(product.get("price"))
    budget_ceiling = gold.get("budget_ceiling")
    expected_band = gold.get("expected_price_band")

    if price is None:
        # Price missing — half credit if not contradicted
        budget_score = 10.0
        scores["details"]["price_issue"] = "price missing or unparseable"
    elif budget_ceiling is not None:
        if price <= budget_ceiling:
            budget_score = 20.0  # Within budget
        elif price <= budget_ceiling * 1.1:
            budget_score = 15.0  # Slightly over
            scores["details"]["price_issue"] = f"price ${price:.0f} slightly over budget ${budget_ceiling:.0f}"
        elif price <= budget_ceiling * 1.25:
            budget_score = 10.0
            scores["details"]["price_issue"] = f"price ${price:.0f} over budget ${budget_ceiling:.0f}"
        else:
            budget_score = 0.0  # Way over budget
            scores["details"]["price_issue"] = f"price ${price:.0f} far exceeds budget ${budget_ceiling:.0f}"
    elif expected_band:
        # Try to parse band
        m = re.search(r"\$?(\d+).*\$?(\d+)", expected_band)
        if m:
            low, high = float(m.group(1)), float(m.group(2))
            if low <= price <= high:
                budget_score = 20.0
            elif price <= high * 1.2:
                budget_score = 15.0
            else:
                budget_score = 5.0
                scores["details"]["price_issue"] = f"price ${price:.0f} outside band {expected_band}"

    scores["budget_price"] = budget_score

    # --- 3. Feature Match (20 points) ---
    must_have = gold.get("must_have_features", [])
    if must_have:
        matched = sum(1 for f in must_have if _text_contains_feature(product_text, f))
        feature_ratio = matched / len(must_have)
        feature_score = 20.0 * feature_ratio
        scores["details"]["features_matched"] = f"{matched}/{len(must_have)}"
        scores["details"]["features_missing"] = [
            f for f in must_have if not _text_contains_feature(product_text, f)
        ]
    else:
        feature_score = 20.0  # No features to check
    scores["feature_match"] = feature_score

    # --- 4. Link Integrity (20 points) ---
    url = product.get("url", "")
    cheapest_link = product.get("cheapest_link", "")
    link_score = 0.0

    # Main URL (10 points)
    url_check = link_checks.get(url, {"reachable": False, "is_product_page": False})
    if url_check.get("reachable") and url_check.get("is_product_page"):
        link_score += 10.0
    elif url_check.get("reachable"):
        link_score += 5.0
        scores["details"]["url_issue"] = url_check.get("reason", "not a product page")
    else:
        scores["details"]["url_issue"] = url_check.get("reason", "unreachable")

    # Cheapest link (10 points)
    if cheapest_link and cheapest_link != url:
        cl_check = link_checks.get(cheapest_link, {"reachable": False, "is_product_page": False})
        if cl_check.get("reachable") and cl_check.get("is_product_page"):
            link_score += 10.0
        elif cl_check.get("reachable"):
            link_score += 5.0
            scores["details"]["cheapest_link_issue"] = cl_check.get("reason", "not a product page")
        else:
            scores["details"]["cheapest_link_issue"] = cl_check.get("reason", "unreachable")
    elif cheapest_link == url:
        # Same as main URL — use same result
        if url_check.get("reachable") and url_check.get("is_product_page"):
            link_score += 10.0
        elif url_check.get("reachable"):
            link_score += 5.0
    else:
        scores["details"]["cheapest_link_issue"] = "no cheapest link provided"

    scores["link_integrity"] = link_score

    # --- 5. Evidence Completeness (15 points) ---
    evidence_score = 0.0
    # Rating present and valid (3 pts)
    rating = product.get("rating")
    if rating is not None and isinstance(rating, (int, float)) and 1 <= rating <= 5:
        evidence_score += 3.0

    # Pros list non-empty (3 pts)
    if product.get("pros") and len(product["pros"]) > 0:
        evidence_score += 3.0

    # Cons list non-empty (3 pts)
    if product.get("cons") and len(product["cons"]) > 0:
        evidence_score += 3.0

    # At least 1 price_comparison entry (3 pts)
    if product.get("price_comparison") and len(product["price_comparison"]) > 0:
        evidence_score += 3.0

    # why_to_buy present (3 pts)
    if product.get("why_to_buy") and len(str(product["why_to_buy"]).strip()) > 10:
        evidence_score += 3.0

    scores["evidence_completeness"] = evidence_score

    # --- Total ---
    scores["total"] = (
        scores["relevance"]
        + scores["budget_price"]
        + scores["feature_match"]
        + scores["link_integrity"]
        + scores["evidence_completeness"]
    )

    return scores


# ---------------------------------------------------------------------------
# Query-level scoring
# ---------------------------------------------------------------------------

def score_recommendation_alignment(response: dict, product_scores: list[dict], gold: dict) -> float:
    """Score recommendation alignment (out of 100).

    40 — top pick consistent with highest-scoring product
    40 — no contradiction of gold constraints (budget)
    20 — rationale grounded in product fields
    """
    recommendation = str(response.get("final_recommendation", "")).lower()
    products = response.get("products", [])
    score = 0.0

    if not recommendation or not products or not product_scores:
        return 0.0

    # --- Top pick consistency (40 pts) ---
    # Find highest-scoring product
    best_product_idx = max(range(len(product_scores)), key=lambda i: product_scores[i]["total"])
    best_product_name = str(products[best_product_idx].get("name", "")).lower()

    # Check if best product is mentioned in recommendation
    best_name_words = [w for w in re.findall(r"\w+", best_product_name) if len(w) > 2]
    if best_name_words:
        mention_ratio = sum(1 for w in best_name_words if w in recommendation) / len(best_name_words)
        if mention_ratio >= 0.5:
            score += 40.0
        elif mention_ratio >= 0.3:
            score += 25.0
        else:
            score += 10.0  # Some credit if recommendation exists
    else:
        score += 20.0  # Can't verify

    # --- No contradiction of gold constraints (40 pts) ---
    budget_ceiling = gold.get("budget_ceiling")
    contradiction = False

    if budget_ceiling:
        # Check if recommendation promotes an over-budget product without acknowledging it
        for p in products:
            price = _parse_price(p.get("price"))
            p_name = str(p.get("name", "")).lower()
            p_name_words = [w for w in re.findall(r"\w+", p_name) if len(w) > 2]
            mentioned = any(w in recommendation for w in p_name_words) if p_name_words else False

            if price and price > budget_ceiling * 1.1 and mentioned:
                # Over-budget product is promoted in recommendation
                budget_words = ["over budget", "exceeds", "above budget", "more expensive", "higher price"]
                if not any(bw in recommendation for bw in budget_words):
                    contradiction = True
                    break

    if not contradiction:
        score += 40.0
    else:
        score += 10.0  # Penalty for budget contradiction

    # --- Rationale grounded (20 pts) ---
    # Check if recommendation references real product attributes
    grounded_signals = 0
    for p in products:
        for field in ("features", "pros", "cons", "why_to_buy"):
            vals = p.get(field, [])
            if isinstance(vals, str):
                vals = [vals]
            for v in vals:
                v_words = [w for w in re.findall(r"\w+", str(v).lower()) if len(w) > 3]
                if any(w in recommendation for w in v_words[:3]):
                    grounded_signals += 1
                    break

    if grounded_signals >= 2:
        score += 20.0
    elif grounded_signals >= 1:
        score += 10.0

    return score


def score_response_integrity(response: dict) -> float:
    """Score response integrity (out of 100).

    Checks schema validity, product count, and placeholder values.
    """
    score = 0.0

    # Schema validity (40 pts)
    if isinstance(response.get("products"), list) and isinstance(
        response.get("final_recommendation"), str
    ):
        score += 40.0
    elif isinstance(response.get("products"), list):
        score += 20.0

    # Product count 1-3 (30 pts)
    products = response.get("products", [])
    if 1 <= len(products) <= 3:
        score += 30.0
    elif len(products) > 3:
        score += 15.0  # Partial credit

    # No empty/placeholder values (30 pts)
    placeholder_count = 0
    for p in products:
        if not p.get("name") or p["name"] == "Unknown Product":
            placeholder_count += 1
        price = str(p.get("price", ""))
        if price in ("Price not available", "Price varies", "", "null", "None", "0"):
            placeholder_count += 1
        if not p.get("url"):
            placeholder_count += 1

    if placeholder_count == 0:
        score += 30.0
    elif placeholder_count <= 2:
        score += 20.0
    elif placeholder_count <= 4:
        score += 10.0

    return score


def score_query(response: dict, gold: dict, link_checks: dict) -> dict:
    """Score a single query response.

    Returns dict with query_score, product_scores, and breakdowns.
    """
    products = response.get("products", [])

    # Score each product
    product_scores = []
    for p in products:
        ps = score_product(p, gold, link_checks)
        ps["product_name"] = p.get("name", "Unknown")
        product_scores.append(ps)

    # Mean product score
    if product_scores:
        mean_product_score = sum(ps["total"] for ps in product_scores) / len(product_scores)
    else:
        mean_product_score = 0.0

    # Recommendation alignment
    rec_alignment = score_recommendation_alignment(response, product_scores, gold)

    # Response integrity
    resp_integrity = score_response_integrity(response)

    # Query score
    query_score = (
        0.70 * mean_product_score
        + 0.20 * rec_alignment
        + 0.10 * resp_integrity
    )

    # Classify failures
    failures = classify_failures(products, gold, link_checks)

    return {
        "query_id": gold["query_id"],
        "query_text": gold["query_text"],
        "category": gold["category"],
        "difficulty": gold["difficulty"],
        "query_score": round(query_score, 2),
        "mean_product_score": round(mean_product_score, 2),
        "recommendation_alignment": round(rec_alignment, 2),
        "response_integrity": round(resp_integrity, 2),
        "product_count": len(products),
        "product_scores": product_scores,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

def classify_failures(products: list[dict], gold: dict, link_checks: dict) -> list[str]:
    """Classify failures into taxonomy categories.

    Categories:
        wrong_product_type
        budget_violation
        invalid_main_link
        invalid_cheapest_link
        missing_invalid_price
        weak_feature_match
        unsupported_recommendation
    """
    failures = []
    gold_type = gold.get("product_type", "").lower()
    budget_ceiling = gold.get("budget_ceiling")
    must_have = gold.get("must_have_features", [])

    for p in products:
        product_text = f"{p.get('name', '')} {' '.join(str(f) for f in p.get('features', []))}".lower()

        # Wrong product type
        type_words = [w for w in re.findall(r"\w+", gold_type) if len(w) > 2]
        if type_words:
            match_ratio = sum(1 for w in type_words if w in product_text) / len(type_words)
            if match_ratio < 0.3:
                failures.append("wrong_product_type")

        # Budget violation
        price = _parse_price(p.get("price"))
        if budget_ceiling and price and price > budget_ceiling * 1.1:
            failures.append("budget_violation")

        # Invalid main link
        url = p.get("url", "")
        url_check = link_checks.get(url, {"reachable": False, "is_product_page": False})
        if not url_check.get("reachable") or not url_check.get("is_product_page"):
            failures.append("invalid_main_link")

        # Invalid cheapest link
        cl = p.get("cheapest_link", "")
        if cl and cl != url:
            cl_check = link_checks.get(cl, {"reachable": False, "is_product_page": False})
            if not cl_check.get("reachable") or not cl_check.get("is_product_page"):
                failures.append("invalid_cheapest_link")

        # Missing/invalid price
        if price is None:
            failures.append("missing_invalid_price")

        # Weak feature match
        if must_have:
            matched = sum(1 for f in must_have if _text_contains_feature(product_text, f))
            if matched / len(must_have) < 0.4:
                failures.append("weak_feature_match")

    return list(set(failures))  # Deduplicate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Score Maven evaluation run")
    parser.add_argument("--run", required=True, help="Path to run directory")
    parser.add_argument("--gold", required=True, help="Path to gold.jsonl")
    parser.add_argument("--skip-link-checks", action="store_true",
                        help="Skip HTTP link verification (faster, less accurate)")
    args = parser.parse_args()

    run_dir = pathlib.Path(args.run)
    responses_dir = run_dir / "responses"

    if not responses_dir.exists():
        print(f"Error: responses directory not found at {responses_dir}")
        sys.exit(1)

    # Load gold
    gold_entries = {}
    with open(args.gold) as f:
        for line in f:
            line = line.strip()
            if line:
                g = json.loads(line)
                gold_entries[g["query_id"]] = g

    print(f"Loaded {len(gold_entries)} gold entries")

    # Load responses
    responses = {}
    for resp_file in responses_dir.glob("*.json"):
        qid = resp_file.stem
        try:
            with open(resp_file) as f:
                responses[qid] = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  Warning: could not load {resp_file.name}: {e}")
            responses[qid] = {"products": [], "final_recommendation": ""}

    print(f"Loaded {len(responses)} responses")

    # Collect all URLs for batch link checking
    all_urls = set()
    if not args.skip_link_checks:
        for resp in responses.values():
            for p in resp.get("products", []):
                url = p.get("url", "")
                if url and url.startswith("http"):
                    all_urls.add(url)
                cl = p.get("cheapest_link", "")
                if cl and cl.startswith("http"):
                    all_urls.add(cl)

        print(f"Checking {len(all_urls)} unique URLs...")
        link_checks = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(_check_url_reachable, url): url for url in all_urls
            }
            done_count = 0
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    link_checks[url] = future.result()
                except Exception as e:
                    link_checks[url] = {"reachable": False, "is_product_page": False, "reason": str(e)}
                done_count += 1
                if done_count % 20 == 0:
                    print(f"  Checked {done_count}/{len(all_urls)} URLs")

        reachable = sum(1 for v in link_checks.values() if v["reachable"])
        product_pages = sum(1 for v in link_checks.values() if v["is_product_page"])
        print(f"  Reachable: {reachable}/{len(all_urls)}, Product pages: {product_pages}/{len(all_urls)}")
    else:
        print("Skipping link checks (--skip-link-checks)")
        link_checks = {}

    # Score each query
    print("\nScoring queries...")
    query_results = []
    for qid in sorted(gold_entries.keys()):
        gold = gold_entries[qid]
        response = responses.get(qid)

        if response is None:
            # Missing response — score as zero
            query_results.append({
                "query_id": qid,
                "query_text": gold["query_text"],
                "category": gold["category"],
                "difficulty": gold["difficulty"],
                "query_score": 0.0,
                "mean_product_score": 0.0,
                "recommendation_alignment": 0.0,
                "response_integrity": 0.0,
                "product_count": 0,
                "product_scores": [],
                "failures": ["missing_response"],
            })
            continue

        result = score_query(response, gold, link_checks)
        query_results.append(result)

    # Compute overall metrics
    if query_results:
        query_accuracy = sum(r["query_score"] for r in query_results) / len(query_results)
        all_product_scores = [
            ps["total"]
            for r in query_results
            for ps in r["product_scores"]
        ]
        product_accuracy = (
            sum(all_product_scores) / len(all_product_scores) if all_product_scores else 0.0
        )
    else:
        query_accuracy = 0.0
        product_accuracy = 0.0

    # Category-wise
    from collections import defaultdict
    cat_scores = defaultdict(list)
    diff_scores = defaultdict(list)
    failure_counts = defaultdict(int)

    for r in query_results:
        cat_scores[r["category"]].append(r["query_score"])
        diff_scores[r["difficulty"]].append(r["query_score"])
        for f in r["failures"]:
            failure_counts[f] += 1

    cat_accuracy = {k: sum(v) / len(v) for k, v in cat_scores.items()}
    diff_accuracy = {k: sum(v) / len(v) for k, v in diff_scores.items()}

    # Build output
    scores_output = {
        "run_id": run_dir.name,
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries": len(query_results),
        "total_products": sum(r["product_count"] for r in query_results),
        "query_accuracy": round(query_accuracy, 2),
        "product_accuracy": round(product_accuracy, 2),
        "passing": query_accuracy >= 60.0,
        "category_accuracy": {k: round(v, 2) for k, v in sorted(cat_accuracy.items())},
        "difficulty_accuracy": {k: round(v, 2) for k, v in sorted(diff_accuracy.items())},
        "failure_taxonomy": dict(sorted(failure_counts.items(), key=lambda x: -x[1])),
        "query_results": query_results,
    }

    # Save scores
    scores_path = run_dir / "scores.json"
    with open(scores_path, "w") as f:
        json.dump(scores_output, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"SCORING RESULTS — {run_dir.name}")
    print(f"{'='*60}")
    print(f"  Query Accuracy:   {query_accuracy:.1f}%  {'✓ PASS' if query_accuracy >= 60 else '✗ FAIL'}")
    print(f"  Product Accuracy: {product_accuracy:.1f}%")
    print(f"  Total Queries:    {len(query_results)}")
    print(f"  Total Products:   {scores_output['total_products']}")
    print()
    print("  Category Accuracy:")
    for cat, acc in sorted(cat_accuracy.items()):
        print(f"    {cat:25s} {acc:.1f}%")
    print()
    print("  Difficulty Accuracy:")
    for diff, acc in sorted(diff_accuracy.items()):
        print(f"    {diff:10s} {acc:.1f}%")
    print()
    print("  Failure Taxonomy:")
    for fail, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
        print(f"    {fail:30s} {count}")
    print()
    print(f"  Scores saved to: {scores_path}")


if __name__ == "__main__":
    main()
