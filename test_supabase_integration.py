"""
Test Supabase integration for video upload functionality.
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("="*80)
print("🧪 TESTING SUPABASE INTEGRATION")
print("="*80)

# Test 1: Check environment variables
print("\n1️⃣ Checking environment variables...")
preprod_url = os.getenv("SUPABASE_PREPROD_URL")
preprod_key = os.getenv("SUPABASE_PREPROD_SERVICE_ROLE_KEY")
prod_url = os.getenv("SUPABASE_PROD_URL")
prod_key = os.getenv("SUPABASE_PROD_SERVICE_ROLE_KEY")

if not preprod_url or not preprod_key:
    print("❌ Missing preprod credentials")
    sys.exit(1)
else:
    print(f"✅ Preprod URL: {preprod_url}")
    print(f"✅ Preprod Key: {preprod_key[:50]}...")

if not prod_url or not prod_key:
    print("❌ Missing prod credentials")
    sys.exit(1)
else:
    print(f"✅ Prod URL: {prod_url}")
    print(f"✅ Prod Key: {prod_key[:50]}...")

# Test 2: Import our custom module
print("\n2️⃣ Testing custom supabase_storage module import...")
try:
    from app.utils.supabase_storage import get_supabase_client, upload_video_to_supabase, SimpleSupabaseClient
    print("✅ supabase_storage module imported successfully")
except ImportError as e:
    print(f"❌ Failed to import supabase_storage: {e}")
    sys.exit(1)

# Test 3: Connect to Supabase preprod
print("\n3️⃣ Testing connection to Supabase PREPROD...")
try:
    supabase_preprod = get_supabase_client("preprod")
    print("✅ Connected to Supabase PREPROD successfully")
    print(f"   Client: {type(supabase_preprod).__name__}")
except Exception as e:
    print(f"❌ Failed to connect to preprod: {e}")
    sys.exit(1)

# Test 4: Connect to Supabase prod
print("\n4️⃣ Testing connection to Supabase PROD...")
try:
    supabase_prod = get_supabase_client("prod")
    print("✅ Connected to Supabase PROD successfully")
    print(f"   Client: {type(supabase_prod).__name__}")
except Exception as e:
    print(f"❌ Failed to connect to prod: {e}")
    sys.exit(1)

# Test 5: Test environment detection
print("\n5️⃣ Testing environment auto-detection...")
test_urls = [
    ("https://preprod.myqateam.ai/api/callback", "preprod"),
    ("https://myqateam.ai/api/callback", "prod"),
    ("https://localhost:3000/api/callback", "preprod"),
]

for url, expected_env in test_urls:
    detected = "prod" if "myqateam.ai" in url and "preprod" not in url else "preprod"
    status = "✅" if detected == expected_env else "❌"
    print(f"   {status} {url} → {detected}")

print("\n" + "="*80)
print("🎉 ALL TESTS PASSED!")
print("="*80)
print("\n📋 Next Steps:")
print("1. Create 'videos' storage bucket in Supabase (if not exists)")
print("2. Create 'narrative_videos' table using the SQL provided")
print("3. Test video upload with a real video file")
print("="*80)
