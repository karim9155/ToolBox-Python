"""
Simple test for async callback workflow - tests locally without mock server.
Uses webhook.site for receiving callbacks.
"""
import requests
import uuid
import json
import time
from PIL import Image, ImageDraw, ImageFont

# Create a simple test image
print("📸 Creating test image...")
img = Image.new('RGB', (1280, 720), color='#4A90E2')
draw = ImageDraw.Draw(img)

# Add text
try:
    # Try to use a system font
    font = ImageFont.truetype("arial.ttf", 60)
except:
    font = ImageFont.load_default()

# Draw text in center
text = "Test Slide"
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
x = (1280 - text_width) / 2
y = (720 - text_height) / 2
draw.text((x, y), text, fill='white', font=font)

# Save test image
test_image_path = 'test_simple_slide.png'
img.save(test_image_path)
print(f"✅ Test image created: {test_image_path}")

# Prepare test data
job_id = str(uuid.uuid4())
print(f"\n📋 Job ID: {job_id}")

script_data = [
    {
        "page_number": 1,
        "voice_over": "Ceci est un test de la génération vidéo asynchrone avec callback.",
        "slide_title": "Test Async"
    }
]

print("\n" + "="*80)
print("TEST: Async Callback Mode")
print("="*80)

# Use webhook.site URL (you can also use your own callback endpoint)
webhook_url = input("\n📌 Enter your webhook.site URL (or press Enter to use localhost:5000): ").strip()
if not webhook_url:
    webhook_url = "http://localhost:5000/api/callback"

print(f"\n🎯 Using callback URL: {webhook_url}")

files = {
    'files': (test_image_path, open(test_image_path, 'rb'), 'image/png')
}

data = {
    'script': json.dumps(script_data),
    'language': 'fr-FR',
    'jobId': job_id,
    'callbackUrl': webhook_url,
    'callbackSecret': 'test-secret-123',
    'documentId': 'doc-test-001',
    'projectId': 'project-test-001'
}

print(f"\n📤 Sending async request to http://127.0.0.1:8000/api/generate-narrative...")

try:
    response = requests.post(
        'http://127.0.0.1:8000/api/generate-narrative',
        files=files,
        data=data,
        timeout=10
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    
    if response.status_code == 202:
        result = response.json()
        print(f"✅ Request accepted!")
        print(f"   Job ID: {result.get('jobId')}")
        print(f"   Message: {result.get('message')}")
        print(f"   Estimated Time: {result.get('estimatedTime')}")
        
        print(f"\n⏳ Job is processing in background...")
        print(f"   Watch the server logs for detailed progress")
        
        if 'localhost' not in webhook_url and '127.0.0.1' not in webhook_url:
            print(f"\n   🌐 Check your callback URL for results: {webhook_url}")
        
        # Poll job status
        print(f"\n📊 Polling job status every 5 seconds...")
        for i in range(60):  # Poll for up to 5 minutes
            time.sleep(5)
            
            try:
                status_response = requests.get(
                    f'http://127.0.0.1:8000/api/narrative-job/{job_id}',
                    timeout=5
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    current_status = status_data.get('status')
                    print(f"   [{i*5}s] Status: {current_status}")
                    
                    if current_status == 'completed':
                        print(f"\n🎉 Job completed successfully!")
                        print(f"   Video Count: {status_data.get('videoCount')}")
                        if 'localhost' not in webhook_url and '127.0.0.1' not in webhook_url:
                            print(f"\n   Check your callback URL for the video data!")
                        break
                    elif current_status == 'failed':
                        print(f"\n❌ Job failed!")
                        print(f"   Error: {status_data.get('error')}")
                        break
                    elif current_status == 'callback_failed':
                        print(f"\n⚠️ Job completed but callback failed!")
                        print(f"   Video Count: {status_data.get('videoCount')}")
                        print(f"   Check server logs for callback errors")
                        break
                else:
                    print(f"   [{i*5}s] Status check failed: {status_response.status_code}")
            
            except requests.exceptions.RequestException as e:
                print(f"   [{i*5}s] Status check error: {e}")
        else:
            print(f"\n⏰ Timeout reached (5 minutes)")
            print(f"   Check server logs for job status")
    
    elif response.status_code == 400:
        print(f"❌ Bad Request: {response.json()}")
    else:
        print(f"❌ Unexpected response: {response.status_code}")
        print(f"   {response.text}")

except requests.exceptions.RequestException as e:
    print(f"\n❌ Request failed: {e}")
    print(f"\n💡 Make sure the API server is running on http://127.0.0.1:8000")

print("\n" + "="*80)
print("Test complete!")
print("="*80)
