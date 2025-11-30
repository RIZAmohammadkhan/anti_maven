#!/usr/bin/env python3
"""Test script to verify enhanced image and price comparison features"""

from agent_graph import app as graph_app
import json

def test_product_search():
    print("=" * 80)
    print("Testing Enhanced Product Search with Images and Price Comparison")
    print("=" * 80)
    
    query = "best wireless headphones"
    print(f"\nQuery: {query}\n")
    
    initial_state = {
        "query": query,
        "product_candidates": [],
        "detailed_reports": [],
        "final_response": {}
    }
    
    try:
        result = graph_app.invoke(initial_state)
        final_response = result.get("final_response", {})
        
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        
        products = final_response.get("products", [])
        print(f"\nFound {len(products)} products:\n")
        
        for i, product in enumerate(products, 1):
            print(f"\n{i}. {product.get('name', 'Unknown Product')}")
            print(f"   Price: {product.get('price', 'N/A')}")
            print(f"   Rating: {product.get('rating', 'N/A')}")
            
            # Image URLs
            image_urls = product.get('image_urls', [])
            if image_urls:
                print(f"   Images found: {len(image_urls)}")
                print(f"   Primary image: {image_urls[0][:80]}...")
            else:
                print(f"   Images: None found")
            
            # Price comparison
            price_comparison = product.get('price_comparison', [])
            if price_comparison:
                print(f"   Price comparison ({len(price_comparison)} retailers):")
                for retailer_info in price_comparison[:3]:  # Show top 3
                    print(f"     - {retailer_info.get('retailer', 'N/A')}: {retailer_info.get('price', 'N/A')}")
                    print(f"       URL: {retailer_info.get('url', 'N/A')[:60]}...")
            
            # Cheapest link
            cheapest_link = product.get('cheapest_link', '')
            if cheapest_link:
                print(f"   Cheapest option: {cheapest_link[:70]}...")
            
            print(f"   Product URL: {product.get('url', 'N/A')[:70]}...")
            
        print("\n" + "-" * 80)
        print("RECOMMENDATION:")
        print("-" * 80)
        print(final_response.get("final_recommendation", "No recommendation available"))
        print("\n" + "=" * 80)
        
        # Save detailed results to file
        with open('/home/rmk/Projects/anti_maven/test_results.json', 'w') as f:
            json.dump(final_response, f, indent=2)
        print("\nDetailed results saved to test_results.json")
        
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_product_search()
