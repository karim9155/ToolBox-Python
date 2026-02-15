# Quick Start Guide - Testing Async Callback

## Prerequisites

Make sure your ToolBox API is running:
```bash
# If not already running:
docker-compose up -d
# OR
uvicorn app.main:app --reload --port 8000
```

## Option 1: Automated Test (Recommended)

The test script includes a mock callback server and tests both modes.

### Step 1: Install Flask for the test server
```bash
pip install flask
```

### Step 2: Run the test
```bash
python test_async_callback.py
```

**What it does:**
1. Starts a mock callback server on port 5000
2. Tests async mode (with callback)
3. Tests sync mode (original behavior)
4. Shows callback payloads in console

## Option 2: Manual cURL Test

### Test Async Mode

```bash
# Generate a job ID
JOB_ID=$(python -c "import uuid; print(uuid.uuid4())")

# Make the request
curl -X POST http://localhost:8000/api/generate-narrative \
  -F "files=@test_output_local/slide_1.png" \
  -F 'script=[{"page_number":1,"voice_over":"Test audio","slide_title":"Test"}]' \
  -F "language=fr-FR" \
  -F "jobId=$JOB_ID" \
  -F "callbackUrl=https://webhook.site/your-unique-url" \
  -F "callbackSecret=test-secret-123"

# Expected response (HTTP 202):
# {
#   "success": true,
#   "jobId": "uuid-here",
#   "message": "Video generation started",
#   "estimatedTime": "10-15 minutes"
# }

# Poll job status
curl http://localhost:8000/api/narrative-job/$JOB_ID
```

### Test Sync Mode (Backwards Compatibility)

```bash
# Same request without callbackUrl
curl -X POST http://localhost:8000/api/generate-narrative \
  -F "files=@test_output_local/slide_1.png" \
  -F 'script=[{"page_number":1,"voice_over":"Test","slide_title":"Test"}]' \
  -F "language=fr-FR" \
  -o output.zip

# Expected: ZIP file downloaded immediately
unzip -l output.zip
```

## Option 3: Python Script Test

```python
import requests
import uuid

job_id = str(uuid.uuid4())

# Prepare request
files = {'files': open('test_output_local/slide_1.png', 'rb')}
data = {
    'script': '[{"page_number":1,"voice_over":"Test","slide_title":"Test"}]',
    'language': 'fr-FR',
    'jobId': job_id,
    'callbackUrl': 'https://webhook.site/your-unique-url',
    'callbackSecret': 'test-secret'
}

# Send async request
response = requests.post(
    'http://localhost:8000/api/generate-narrative',
    files=files,
    data=data
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
print(f"Job ID: {job_id}")

# Poll status
import time
time.sleep(5)
status = requests.get(f'http://localhost:8000/api/narrative-job/{job_id}')
print(f"Job Status: {status.json()}")
```

## Using webhook.site for Testing

If you don't have a callback endpoint yet:

1. Visit https://webhook.site/
2. Copy your unique URL (e.g., `https://webhook.site/abc-123-def`)
3. Use it as `callbackUrl` in your test
4. Watch the webhook.site page - you'll see the callback POST arrive

## Verify Callback Payload

When the callback arrives, you should see:

**Success:**
```json
{
  "jobId": "your-job-id",
  "status": "completed",
  "videos": [
    {
      "filename": "part_01.mp4",
      "data": "base64-encoded-video...",
      "index": 0
    }
  ],
  "metadata": {
    "totalDuration": 5.2,
    "videoCount": 1,
    "processingTime": 45.3,
    "ttsCost": 0.001,
    "ttsCharacters": 123,
    "voiceName": "fr-FR-Neural2-B"
  }
}
```

**Failure:**
```json
{
  "jobId": "your-job-id",
  "status": "failed",
  "error": "Error message here",
  "failedAt": "video_generation",
  "processingTime": 12.5
}
```

## Troubleshooting

### "Invalid or disallowed callback URL"
- Set `ALLOWED_CALLBACK_DOMAINS=` (empty) in your environment to allow all domains
- Or add your domain: `ALLOWED_CALLBACK_DOMAINS=webhook.site,yourdomain.com`

### Callback not received
1. Check ToolBox logs for errors
2. Verify your callback endpoint returns HTTP 200
3. Use webhook.site to test without implementing your own endpoint

### Job shows "processing" forever
- Check ToolBox container logs: `docker logs -f <container-id>`
- Look for errors in video generation
- Poll `/narrative-job/{jobId}` to see if status changed to "failed"

### Test files missing
```bash
# Create a simple test image if needed
mkdir -p test_output_local
convert -size 1280x720 xc:blue -pointsize 60 -draw "text 400,360 'Test Slide'" test_output_local/slide_1.png
```

## Next Steps

Once testing is complete:
1. Implement your callback endpoint (see [example_integration.py](example_integration.py))
2. Add environment variables to production
3. Deploy and test with real PDF/image files
4. Monitor logs for callback failures

## Environment Variables (Optional)

```bash
# Add to .env or docker-compose.yml
CALLBACK_TIMEOUT=30
MAX_CALLBACK_RETRIES=3
ALLOWED_CALLBACK_DOMAINS=yourdomain.com,webhook.site
```

Restart after changes:
```bash
docker-compose restart api
```
