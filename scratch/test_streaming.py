import sys
import os
import asyncio
import json

# Add backend directory to sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from orchestrator.master_llm import MasterOrchestrator

async def test_streaming():
    print("=========================================")
    print("📡 Testing Live Response Streaming...")
    print("=========================================")
    
    orchestrator = MasterOrchestrator()
    query = "Say 'Hello, this is a streaming test!' in exactly one sentence."
    
    print(f"Query: {query}\n")
    print("--> Processing Stream:")
    
    chunks_received = 0
    full_response_received = False
    accumulated_text = []
    
    async for event_str in orchestrator.process_query_stream(query):
        event = json.loads(event_str)
        
        # Check if it is a streaming chunk
        if event.get("model") == "Final Response" and event.get("status") == "Processing" and event.get("action") == "Streaming":
            chunk = event.get("details", {}).get("answer_chunk", "")
            accumulated_text.append(chunk)
            chunks_received += 1
            # Print chunk with brackets to show tokenization boundaries
            print(f"[{chunk}]", end="", flush=True)
            
        elif event.get("model") == "Final Response" and event.get("status") == "Completed":
            print("\n\n--> Final Response Received!")
            details = event.get("details", {})
            print(f"Answer: {details.get('answer')}")
            print(f"Sources: {details.get('sources')}")
            full_response_received = True
            
    print("\n=========================================")
    print(f"Total chunks received: {chunks_received}")
    print(f"Full response received: {full_response_received}")
    print(f"Accumulated text: {''.join(accumulated_text)}")
    print("=========================================")
    
    assert chunks_received > 0, "Should receive multiple text chunks during streaming"
    assert full_response_received, "Should receive a final Completed response event"
    print("🎉 STREAMING FUNCTIONAL TEST PASSED!")

if __name__ == "__main__":
    asyncio.run(test_streaming())
