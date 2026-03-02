#!/usr/bin/env python3
"""Quick test to verify Azure is responding to input"""

import os
import threading
from cli import AzureModelsClient

def test_azure():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ Error: GITHUB_TOKEN not set")
        return False
    
    print(f"✓ Token found: {token[:20]}...")
    
    try:
        # Initialize Azure client
        client = AzureModelsClient(token=token)
        print("✓ Azure client initialized")
        
        # Test with a simple prompt
        test_messages = [
            {"role": "user", "content": "Say 'Hello, Azure is working!' and nothing else."}
        ]
        
        print("\n📤 Sending test prompt to Azure...")
        print("⏳ Waiting for response (timeout set to 10 seconds)...\n")
        
        result = {"response": None, "error": None}
        
        def make_request():
            try:
                result["response"] = client.complete(test_messages)
            except Exception as e:
                result["error"] = e
        
        # Run in thread with timeout
        thread = threading.Thread(target=make_request, daemon=True)
        thread.start()
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            print(f"⏱️  Request timed out after 10 seconds")
            print("\nAzure API appears to be responding (no connection error),")
            print("but the request took too long. This could indicate:")
            print("  • Rate limiting")
            print("  • Server overload")
            print("  • Network latency")
            return False
        
        if result["error"]:
            print(f"❌ Error communicating with Azure: {result['error']}")
            print(f"Error type: {type(result['error']).__name__}")
            return False
        
        print(f"✓ Azure responded successfully!")
        print(f"Response: {result['response']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_azure()
    exit(0 if success else 1)
