#!/usr/bin/env python3
"""
Script to check if a Vertex AI model exists and is accessible
"""
import os
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
from google.cloud import aiplatform
from google.api_core import exceptions

# Your configuration
TUNED_MODEL_ID = "projects/1034262682760/locations/us-central1/models/2268735591287881728@1"
CREDS_PATH = "gcp_creds.json"  # Update this path

def parse_model_id(model_id):
    """Parse the model ID to extract project, location, and model details"""
    parts = model_id.split('/')
    if len(parts) < 6:
        raise ValueError(f"Invalid model ID format: {model_id}")
    
    return {
        'project_id': parts[1],
        'location': parts[3], 
        'model_id': parts[5]
    }

def check_model_exists():
    print("🔍 Checking if your tuned model exists and is accessible...\n")
    
    try:
        # Parse model ID
        model_info = parse_model_id(TUNED_MODEL_ID)
        print(f"📋 Model Info:")
        print(f"   Project: {model_info['project_id']}")
        print(f"   Location: {model_info['location']}")
        print(f"   Model ID: {model_info['model_id']}\n")
        
        # Load credentials
        if not os.path.exists(CREDS_PATH):
            print(f"❌ Credentials file not found: {CREDS_PATH}")
            return False
            
        credentials = service_account.Credentials.from_service_account_file(CREDS_PATH)
        print(f"✅ Loaded credentials from: {CREDS_PATH}")
        
        # Initialize Vertex AI
        vertexai.init(
            project=model_info['project_id'], 
            location=model_info['location'], 
            credentials=credentials
        )
        print("✅ Vertex AI initialized")
        
        # Method 1: Try to create GenerativeModel instance
        print("\n🧪 Test 1: Creating GenerativeModel instance...")
        try:
            model = GenerativeModel(model_name=TUNED_MODEL_ID)
            print("✅ GenerativeModel created successfully")
        except Exception as e:
            print(f"❌ Failed to create GenerativeModel: {e}")
            return False
        
        # Method 2: Try a simple generation call
        print("\n🧪 Test 2: Testing model generation...")
        try:
            response = model.generate_content("Hello")
            print("✅ Model responded successfully!")
            print(f"   Response: {response.text[:100]}...")
        except exceptions.NotFound:
            print("❌ Model not found - the model ID doesn't exist")
            return False
        except exceptions.PermissionDenied:
            print("❌ Permission denied - your service account lacks access")
            return False
        except exceptions.InvalidArgument as e:
            print(f"❌ Invalid argument error: {e}")
            print("   This might be a prompt formatting issue")
            return False
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            return False
            
        # Method 3: List models to verify (if permissions allow)
        print("\n🧪 Test 3: Listing available models...")
        try:
            aiplatform.init(
                project=model_info['project_id'],
                location=model_info['location'],
                credentials=credentials
            )
            
            models = aiplatform.Model.list(
                filter=f'display_name="*"',
                order_by="create_time desc"
            )
            
            print(f"✅ Found {len(models)} models in your project")
            
            # Check if our specific model is in the list
            target_model_found = False
            for model in models[:10]:  # Show first 10
                model_resource_name = model.resource_name
                print(f"   📄 {model.display_name} - {model_resource_name}")
                if model_info['model_id'] in model_resource_name:
                    target_model_found = True
                    print("      ⭐ This is your target model!")
            
            if not target_model_found:
                print(f"\n⚠️  Your target model ({model_info['model_id']}) was not found in the model list")
                print("   This could mean:")
                print("   - The model ID is incorrect")
                print("   - The model was deleted")
                print("   - You don't have permission to see it")
                
        except exceptions.PermissionDenied:
            print("⚠️  Cannot list models (permission denied)")
        except Exception as e:
            print(f"⚠️  Error listing models: {e}")
        
        print("\n🎉 Model check completed!")
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_base_models():
    """Test with base Gemini models to verify setup works"""
    print("\n🧪 Testing base models for comparison...")
    
    base_models = [
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    
    for model_name in base_models:
        try:
            model = GenerativeModel(model_name=model_name)
            response = model.generate_content("Say hello")
            print(f"✅ {model_name}: {response.text[:50]}...")
        except Exception as e:
            print(f"❌ {model_name}: {e}")

if __name__ == "__main__":
    success = check_model_exists()
    
    if not success:
        print("\n" + "="*50)
        print("🚨 MODEL CHECK FAILED")
        print("="*50)
        print("\nTroubleshooting steps:")
        print("1. Verify your model ID in Google Cloud Console")
        print("2. Check service account permissions")
        print("3. Try testing with base models first")
        print("\nTesting base models now...\n")
        test_base_models()
    else:
        print("\n✅ Your model appears to be working correctly!")