import sys
import os

# Add backend directory to sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from utils.cache import ResponseCache

def test_cache_functionality():
    print("=========================================")
    print("⚙️ Testing ResponseCache Utility...")
    print("=========================================")
    
    # 1. Initialize Cache (checks auto-discovery/fallback)
    cache = ResponseCache()
    
    # Define test parameters
    query = "What is the fee for i5 processor?"
    history = "User has an RTX 2050 GPU."
    image_context = "Image contains hardware specs list."
    
    response_payload = {
        "answer": "The fee/price is $299.",
        "sources": ["Image specs", "Web query"],
        "source_map": {"1": "Image specs", "2": "Web query"}
    }
    
    # 2. Test Cache Miss
    print("--> Querying non-existing key...")
    cached_val = cache.get(query, history, image_context)
    print(f"Result: {cached_val} (Expected: None)")
    assert cached_val is None, "Cache miss should return None"
    
    # 3. Test Cache Set
    print("\n--> Writing response to cache...")
    cache.set(query, history, image_context, response_payload, ttl_seconds=10)
    print("Successfully set entry.")
    
    # 4. Test Cache Hit
    print("\n--> Querying existing key...")
    cached_val = cache.get(query, history, image_context)
    print(f"Result: {cached_val}")
    assert cached_val == response_payload, "Cache hit should return identical payload"
    print("✅ Cache Hit verification PASSED!")
    
    # 5. Test Context Sensitivity (Collision Prevention)
    print("\n--> Testing collision prevention (changing query history)...")
    different_val = cache.get(query, "Different history context", image_context)
    print(f"Result with different history: {different_val} (Expected: None)")
    assert different_val is None, "Different context must result in cache miss"
    print("✅ Collision Prevention PASSED!")
    
    print("\n=========================================")
    print("🎉 ALL CACHE TESTS COMPLETED SUCCESSFULLY!")
    print("=========================================")

if __name__ == "__main__":
    test_cache_functionality()
