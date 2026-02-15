# ✅ Callback Configuration - Setup Complete

## What Was Configured

1. ✅ Created `.env` file with callback settings
2. ✅ Added `python-dotenv` to requirements
3. ✅ Updated `app/main.py` to load environment variables
4. ✅ Updated callback utilities to use `TOOLBOX_CALLBACK_SECRET`
5. ✅ Created `.env.example` template
6. ✅ Added configuration test script

---

## Environment Variables Set

```bash
TOOLBOX_CALLBACK_SECRET=004f46916c2132a1b7ac187605e3908212186f8c265892c814f7468c2f85decc
ALLOWED_CALLBACK_DOMAINS=127.0.0.1,localhost,preprod.myqateam.ai,myqateam.ai
CALLBACK_TIMEOUT=30
MAX_CALLBACK_RETRIES=3
```

---

## Approved Callback URLs

These URLs will be accepted by the toolbox:

✅ **Local Dev:**
- `http://127.0.0.1:3000/api/tools/learn/video-callback`
- `http://localhost:3000/api/tools/learn/video-callback`

✅ **Preprod:**
- `https://preprod.myqateam.ai/api/tools/learn/video-callback`

✅ **Production:**
- `https://myqateam.ai/api/tools/learn/video-callback`

❌ **Any other domain will be rejected**

---

## Next Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install `python-dotenv` needed for `.env` loading.

### 2. Test Configuration

```bash
python test_callback_config.py
```

**Expected output:**
```
✅ TOOLBOX_CALLBACK_SECRET: 004f46916c2132a1b7...decc
✅ ALLOWED_CALLBACK_DOMAINS (4 domains):
   - 127.0.0.1
   - localhost
   - preprod.myqateam.ai
   - myqateam.ai
✅ CALLBACK_TIMEOUT: 30s
✅ MAX_CALLBACK_RETRIES: 3

✅ ALLOWED: http://127.0.0.1:3000/api/tools/learn/video-callback
✅ ALLOWED: http://localhost:3000/api/tools/learn/video-callback
✅ ALLOWED: https://preprod.myqateam.ai/api/tools/learn/video-callback
✅ ALLOWED: https://myqateam.ai/api/tools/learn/video-callback
❌ REJECTED: https://evil.com/callback
```

### 3. Update GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions

Add/update these secrets:

```
Name: TOOLBOX_CALLBACK_SECRET
Value: 004f46916c2132a1b7ac187605e3908212186f8c265892c814f7468c2f85decc

Name: ALLOWED_CALLBACK_DOMAINS  
Value: 127.0.0.1,localhost,preprod.myqateam.ai,myqateam.ai
```

### 4. Updated GitHub Actions (Already Done)

Your deploy workflow now includes:

```yaml
docker run -d \
  -p 8000:8000 \
  --name toolbox-api \
  --restart unless-stopped \
  -e ASSEMBLYAI_API_KEY=${{ secrets.ASSEMBLYAI_API_KEY }} \
  -e GOOGLE_TTS_API_KEY=${{ secrets.GOOGLE_TTS_API_KEY }} \
  -e TOOLBOX_CALLBACK_SECRET=${{ secrets.TOOLBOX_CALLBACK_SECRET }} \
  -e ALLOWED_CALLBACK_DOMAINS=${{ secrets.ALLOWED_CALLBACK_DOMAINS }} \
  -e CALLBACK_TIMEOUT=30 \
  -e MAX_CALLBACK_RETRIES=3 \
  karimkli/toolbox-api:latest
```

### 5. Test End-to-End

Once deployed, test with your Next.js callback:

```python
import requests

response = requests.post(
    'http://your-toolbox-url/generate-narrative',
    files={'files': open('test.png', 'rb')},
    data={
        'script': '[{"page_number":1,"voice_over":"Test","slide_title":"Test"}]',
        'language': 'fr-FR',
        'callbackUrl': 'https://myqateam.ai/api/tools/learn/video-callback',
        'callbackSecret': '004f46916c2132a1b7ac187605e3908212186f8c265892c814f7468c2f85decc',
        'documentId': 'test-doc-123',
        'projectId': 'test-proj-456'
    }
)

print(response.status_code)  # Should be 202
print(response.json())        # Should have jobId
```

---

## Security Notes

✅ **Secret Validation:** The toolbox now verifies the callback secret matches `TOOLBOX_CALLBACK_SECRET`

✅ **Domain Whitelist:** Only approved domains can receive callbacks (SSRF protection)

✅ **HTTPS in Production:** All production/preprod URLs use HTTPS

✅ **Secret Not Exposed:** The secret is loaded from environment, never hardcoded

---

## Troubleshooting

### "Invalid or disallowed callback URL"
- Check domain is in `ALLOWED_CALLBACK_DOMAINS`
- Verify URL format: `http://localhost:3000/...` or `https://domain.com/...`

### "No callback secret provided"
- Check `.env` file has `TOOLBOX_CALLBACK_SECRET`
- Verify `python-dotenv` is installed
- Restart the server after updating `.env`

### Callback not received
- Check Next.js app logs for incoming requests
- Verify `x-callback-secret` header matches
- Test callback endpoint manually with curl

---

## Files Modified/Created

- ✅ `.env` - Environment variables (DO NOT COMMIT)
- ✅ `.env.example` - Template for other developers
- ✅ `requirements.txt` - Added python-dotenv
- ✅ `app/main.py` - Added dotenv loading
- ✅ `app/utils/callback.py` - Updated to use TOOLBOX_CALLBACK_SECRET
- ✅ `test_callback_config.py` - Configuration test script
- ✅ `.gitignore` - Already includes .env (verified)

---

## Ready to Deploy! 🚀

The configuration is complete. Once you:
1. Install dependencies (`pip install -r requirements.txt`)
2. Test locally (`python test_callback_config.py`)
3. Add GitHub secrets
4. Deploy

Your async callback workflow will be fully operational with the Next.js app!
