# Async Callback Workflow - Documentation

## Overview

The `/generate-narrative` endpoint now supports **two modes**:

1. **Synchronous mode** (original) - Blocks until videos are ready, returns ZIP file
2. **Async mode** (new) - Returns immediately with HTTP 202, sends results to callback URL

## Quick Start

### Environment Variables

Add to your `.env` file (optional, has defaults):

```bash
CALLBACK_TIMEOUT=30                # Seconds to wait for callback response
MAX_CALLBACK_RETRIES=3             # Number of retry attempts
ALLOWED_CALLBACK_DOMAINS=yourdomain.com,localhost  # Comma-separated allowed domains (empty = allow all)
```

### Async Mode Usage

```python
import requests
import uuid

job_id = str(uuid.uuid4())

files = {
    'files': ('slide.png', open('slide.png', 'rb'), 'image/png')
}

data = {
    'script': json.dumps([{
        "page_number": 1,
        "voice_over": "Hello world",
        "slide_title": "Title"
    }]),
    'language': 'en-US',
    'jobId': job_id,
    'callbackUrl': 'https://yourdomain.com/api/video-callback',
    'callbackSecret': 'your-secret-key',
    'documentId': 'doc-123',  # Optional
    'projectId': 'proj-456'    # Optional
}

response = requests.post(
    'http://localhost:8000/api/generate-narrative',
    files=files,
    data=data
)

# Response: HTTP 202
# {
#   "success": true,
#   "jobId": "uuid-here",
#   "message": "Video generation started",
#   "estimatedTime": "10-15 minutes"
# }
```

### Synchronous Mode Usage (Unchanged)

```python
# Simply omit callbackUrl to use original behavior
data = {
    'script': json.dumps([...]),
    'language': 'fr-FR'
    # No callbackUrl = sync mode
}

response = requests.post(
    'http://localhost:8000/api/generate-narrative',
    files=files,
    data=data
)

# Response: HTTP 200 with ZIP file
with open('output.zip', 'wb') as f:
    f.write(response.content)
```

## Callback Specification

### Success Callback

When video generation completes successfully:

```json
POST https://yourdomain.com/api/video-callback
Content-Type: application/json
x-callback-secret: your-secret-key

{
  "jobId": "uuid-string",
  "status": "completed",
  "documentId": "doc-123",      // If provided
  "projectId": "proj-456",       // If provided
  "videos": [
    {
      "filename": "part_01.mp4",
      "data": "base64EncodedVideoData...",
      "index": 0
    },
    {
      "filename": "part_02.mp4",
      "data": "base64EncodedVideoData...",
      "index": 1
    }
  ],
  "metadata": {
    "totalDuration": 45.3,        // Seconds
    "videoCount": 2,
    "processingTime": 127.5,      // Seconds
    "ttsCost": 0.0012,           // USD
    "ttsCharacters": 250,
    "voiceName": "fr-FR-Neural2-B"
  }
}
```

### Failure Callback

When generation fails:

```json
POST https://yourdomain.com/api/video-callback
Content-Type: application/json
x-callback-secret: your-secret-key

{
  "jobId": "uuid-string",
  "status": "failed",
  "documentId": "doc-123",
  "projectId": "proj-456",
  "error": "FFmpeg encoding failed: ...",
  "failedAt": "video_generation",
  "processingTime": 45.2
}
```

### Your Callback Endpoint Must:

1. **Verify the secret**: Check `x-callback-secret` header matches expected value
2. **Return HTTP 200**: Any other status triggers retry (3 attempts with exponential backoff: 1s → 5s → 15s)
3. **Handle large payloads**: Videos are base64-encoded (~33% larger). Budget for 50-100 MB total payload.
4. **Decode videos**: `base64.b64decode(video['data'])` to get MP4 bytes

Example callback handler:

```python
from fastapi import APIRouter, Request, HTTPException
import base64

router = APIRouter()

@router.post("/video-callback")
async def handle_video_callback(request: Request):
    # Verify secret
    secret = request.headers.get("x-callback-secret")
    if secret != "your-expected-secret":
        raise HTTPException(status_code=403, detail="Invalid secret")
    
    data = await request.json()
    job_id = data["jobId"]
    status = data["status"]
    
    if status == "completed":
        # Save videos
        for video in data["videos"]:
            video_bytes = base64.b64decode(video["data"])
            with open(f"{job_id}_{video['filename']}", "wb") as f:
                f.write(video_bytes)
        
        # Update your database, notify user, etc.
        print(f"Job {job_id} completed: {data['metadata']}")
    
    elif status == "failed":
        # Handle failure
        print(f"Job {job_id} failed: {data['error']}")
    
    return {"success": True}
```

## Job Status Polling (Fallback)

If the callback fails, your frontend can poll the status endpoint:

```bash
GET /api/narrative-job/{jobId}

# Response:
{
  "jobId": "uuid",
  "status": "processing|completed|failed|callback_failed",
  "createdAt": 1234567890.123,
  "updatedAt": 1234567890.456,
  "fileCount": 1,
  "videoCount": 2,  // Only present if completed
  "language": "fr-FR",
  "documentId": "doc-123",
  "projectId": "proj-456",
  "error": "..."  // Only present if failed
}
```

## Security Notes

1. **SSRF Prevention**: Callback URLs are validated against `ALLOWED_CALLBACK_DOMAINS`
2. **Authentication**: Always include `x-callback-secret` header
3. **HTTPS**: Use HTTPS for callback URLs in production (HTTP allowed for localhost)

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /generate-narrative (with callbackUrl)
       │
       v
┌─────────────────────┐
│  FastAPI Router     │
│  (HTTP 202)         │◄─── Returns immediately
└──────┬──────────────┘
       │ Spawns daemon thread
       │
       v
┌─────────────────────┐
│  Background Thread  │
│  - Generate videos  │
│  - Base64 encode    │
│  - POST to callback │
└──────┬──────────────┘
       │
       │ POST /video-callback
       v
┌─────────────────────┐
│  Your Application   │
│  (Receives results) │
└─────────────────────┘
```

## Testing

Run the test suite:

```bash
# Make sure toolbox API is running on port 8000
python test_async_callback.py
```

Or test callback manually:

```bash
curl -X POST http://localhost:8000/api/tools/learn/video-callback \
  -H "Content-Type: application/json" \
  -H "x-callback-secret: test-secret-123" \
  -d '{
    "jobId": "test-123",
    "status": "completed",
    "videos": [
      {
        "filename": "test.mp4",
        "data": "dGVzdA==",
        "index": 0
      }
    ],
    "metadata": {
      "totalDuration": 10.5,
      "videoCount": 1,
      "processingTime": 45.2
    }
  }'
```

## Migration Guide

### Existing Integrations

No changes required! The endpoint is **fully backwards compatible**:
- If you don't send `callbackUrl`, the original synchronous ZIP response is returned
- All existing clients continue to work without modification

### New Integrations

1. Implement callback endpoint in your application
2. Generate a secure random secret (store in env vars)
3. Pass `callbackUrl` and `callbackSecret` when calling `/generate-narrative`
4. Handle both success and failure callback payloads
5. Optional: Poll `/narrative-job/{jobId}` as fallback

## Limitations & Considerations

1. **In-memory job tracking**: Job status won't survive container restarts (fine for single-instance deployments)
2. **Large payloads**: Videos >100MB will trigger warnings. Ensure your callback endpoint accepts large requests.
3. **No video streaming**: Videos are fully generated before callback (same as sync mode)
4. **Thread-based concurrency**: Suitable for ~10 concurrent jobs. For higher scale, consider Celery + Redis.
5. **No job persistence**: If toolbox restarts, pending jobs are lost (frontend will timeout and can retry)

## Troubleshooting

### Callback not received

1. Check toolbox logs for callback errors
2. Verify `x-callback-secret` header is correct
3. Ensure callback endpoint returns HTTP 200
4. Check `ALLOWED_CALLBACK_DOMAINS` env var
5. Poll `/narrative-job/{jobId}` to see job status

### "Invalid or disallowed callback URL"

- Check URL starts with `http://` or `https://`
- Verify domain is in `ALLOWED_CALLBACK_DOMAINS` (or leave empty to allow all)
- For localhost testing, use `http://localhost:port` or `http://127.0.0.1:port`

### Job shows "callback_failed" status

- Callback was attempted but all 3 retries failed
- Check your callback endpoint is reachable and returning 200
- Review toolbox logs for specific error messages
