
import os
import base64
import requests
import json

def test_moondream():
    image_path = "backend/uploads/upload_091c7e34.png"
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    ollama_host = "http://localhost:11434"
    payload = {
        "model": "moondream",
        "prompt": "Analyze this image in detail. Extract text.",
        "images": [image_b64],
        "stream": False,
    }
    
    response = requests.post(f"{ollama_host}/api/generate", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json().get('response')}")

if __name__ == "__main__":
    test_moondream()
