"""
Direct test with requests - simpler approach
"""
import requests
import json
import uuid
from PIL import Image, ImageDraw

print("Creating test image...")
img = Image.new('RGB', (1280, 720), color='#4A90E2')
draw = ImageDraw.Draw(img)
draw.text((500, 350), "Test Slide", fill='white')
img.save('test_slide_simple.png')
print("✅ Test image created")

job_id = str(uuid.uuid4())
print(f"\nJob ID: {job_id}")

# Test with localhost callback (will fail but we can see the flow)
files = {'files': open('test_slide_simple.png', 'rb')}
data = {
    'script': json.dumps([{
        "page_number": 1,
        "voice_over": "Test audio",
        "slide_title": "Test"
    }]),
    'language': 'fr-FR',
    'jobId': job_id,
    'callbackUrl': 'http://localhost:5555/callback',  # Non-existent but valid URL
    'callbackSecret': 'test-secret'
}

print("\nSending request...")
response = requests.post('http://127.0.0.1:8000/generate-narrative', files=files, data=data)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 202:
    print("\n✅ Async mode activated! Check server logs for processing details.")
    
    # Poll status
    import time
    for i in range(6):
        time.sleep(10)
        status_resp = requests.get(f'http://127.0.0.1:8000/narrative-job/{job_id}')
        if status_resp.status_code == 200:
            print(f"[{i*10}s] {status_resp.json()}")
        else:
            print(f"[{i*10}s] Status: {status_resp.status_code}")
