#!/usr/bin/env python3
"""
Helper script to convert Google credentials JSON to base64 for Railway deployment.
"""

import json
import base64
import os

def generate_base64_credentials():
    """Convert google_credentials.json to base64 string for Railway"""
    
    # Path to your Google credentials file
    credentials_file = "google_credentials.json"
    
    if not os.path.exists(credentials_file):
        print(f"❌ Error: {credentials_file} not found!")
        print("Make sure your Google credentials file is in the same directory as this script.")
        return
    
    try:
        # Read the JSON file
        with open(credentials_file, 'r') as f:
            credentials_data = json.load(f)
        
        # Convert to JSON string
        json_string = json.dumps(credentials_data, separators=(',', ':'))
        
        # Encode to base64
        base64_encoded = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
        
        print("✅ Successfully generated base64 credentials!")
        print("\n" + "="*80)
        print("COPY THIS VALUE TO RAILWAY AS 'GOOGLE_CREDENTIALS_B64' ENVIRONMENT VARIABLE:")
        print("="*80)
        print(base64_encoded)
        print("="*80)
        
        print(f"\n📝 Credentials length: {len(base64_encoded)} characters")
        print(f"📄 Original file: {credentials_file}")
        
        # Also save to a file for easy copying
        with open("railway_credentials_b64.txt", "w") as f:
            f.write(base64_encoded)
        
        print(f"💾 Also saved to: railway_credentials_b64.txt")
        print("\n🚀 Ready for Railway deployment!")
        
    except json.JSONDecodeError:
        print(f"❌ Error: {credentials_file} is not valid JSON!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    generate_base64_credentials()