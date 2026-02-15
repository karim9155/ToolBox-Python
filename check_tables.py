import httpx, os, json
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_PROD_URL')
key = os.getenv('SUPABASE_PROD_SERVICE_ROLE_KEY')
headers = {'apikey': key, 'Authorization': f'Bearer {key}'}

document_id = '1e277dfd-bef7-4599-ab1a-d37100c5e4a0'

tables_to_try = [
    'document_slides',
    'document_scripts', 
    'narrativeslides',
    'narrativescripts',
    'slides',
    'scripts',
    'document_images',
    'narrative_slides',
    'narrative_scripts'
]

print("Checking which tables exist:")
for table in tables_to_try:
    try:
        r = httpx.get(
            f'{url}/rest/v1/{table}?document_id=eq.{document_id}&limit=1',
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            print(f"✅ {table}: {r.status_code} ({len(data)} records)")
        else:
            print(f"❌ {table}: {r.status_code}")
    except Exception as e:
        print(f"❌ {table}: {e}")
