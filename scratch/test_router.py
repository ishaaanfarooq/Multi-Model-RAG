
def test_router():
    image_keywords = ["photo", "image", "picture", "screenshot", "uploaded", "this",
                      "describe", "written", "show", "see", "look", "what is", "what's",
                      "tell me about", "analyze", "read", "content", "says", "text in",
                      "summarize this", "explain this", "extract", "info in"]
    
    queries = [
        "tell me what is written in the image",
        "describe this picture",
        "what is in the uploaded file?",
        "analyze this image",
        "read the text in the screenshot"
    ]
    
    for query in queries:
        query_lower = query.lower()
        is_image_centric = any(kw in query_lower for kw in image_keywords)
        print(f"Query: '{query}' -> is_image_centric: {is_image_centric}")

if __name__ == "__main__":
    test_router()
