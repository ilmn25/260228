#!/usr/bin/env python3
"""Debug Azure connection issues"""

import os
import logging
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

token = os.getenv("GITHUB_TOKEN")
if not token:
    print("ERROR: GITHUB_TOKEN not set")
    exit(1)

print(f"[OK] Token found: {token[:20]}...")
print("Initializing Azure client with debug logging...\n")

try:
    client = ChatCompletionsClient(
        endpoint="https://models.inference.ai.azure.com",
        credential=AzureKeyCredential(token),
    )
    
    print("[INFO] Sending minimal test request...\n")
    
    # Try a very simple request
    response = client.complete(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=10
    )
    
    print(f"\n[OK] Success!")
    print(f"Response: {response.choices[0].message['content']}")
    
except Exception as e:
    print(f"\n[ERROR] Error: {type(e).__name__}: {e}")
    if hasattr(e, 'response'):
        print(f"Response status: {e.response.status_code if hasattr(e.response, 'status_code') else 'N/A'}")

