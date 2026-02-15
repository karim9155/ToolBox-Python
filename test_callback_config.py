"""
Test script to verify the callback configuration is loaded correctly.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("="*80)
print("Callback Configuration Test")
print("="*80)

# Check TOOLBOX_CALLBACK_SECRET
callback_secret = os.getenv("TOOLBOX_CALLBACK_SECRET")
if callback_secret:
    print(f"✅ TOOLBOX_CALLBACK_SECRET: {callback_secret[:20]}...{callback_secret[-20:]}")
else:
    print("❌ TOOLBOX_CALLBACK_SECRET: NOT SET")

# Check ALLOWED_CALLBACK_DOMAINS
allowed_domains = os.getenv("ALLOWED_CALLBACK_DOMAINS", "")
if allowed_domains:
    domains = allowed_domains.split(',')
    print(f"\n✅ ALLOWED_CALLBACK_DOMAINS ({len(domains)} domains):")
    for domain in domains:
        print(f"   - {domain}")
else:
    print("\n⚠️ ALLOWED_CALLBACK_DOMAINS: NOT SET (all domains allowed)")

# Check CALLBACK_TIMEOUT
timeout = os.getenv("CALLBACK_TIMEOUT", "30")
print(f"\n✅ CALLBACK_TIMEOUT: {timeout}s")

# Check MAX_CALLBACK_RETRIES
retries = os.getenv("MAX_CALLBACK_RETRIES", "3")
print(f"✅ MAX_CALLBACK_RETRIES: {retries}")

print("\n" + "="*80)
print("Testing callback URL validation")
print("="*80)

# Test URL validation
from urllib.parse import urlparse

def is_allowed_domain(callback_url: str) -> bool:
    allowed = os.getenv('ALLOWED_CALLBACK_DOMAINS', '').split(',')
    parsed = urlparse(callback_url)
    hostname = parsed.hostname or ''
    return hostname in [d.strip() for d in allowed]

test_urls = [
    "http://127.0.0.1:3000/api/tools/learn/video-callback",
    "http://localhost:3000/api/tools/learn/video-callback",
    "https://preprod.myqateam.ai/api/tools/learn/video-callback",
    "https://myqateam.ai/api/tools/learn/video-callback",
    "https://evil.com/callback"  # Should be rejected
]

for url in test_urls:
    result = is_allowed_domain(url)
    status = "✅ ALLOWED" if result else "❌ REJECTED"
    print(f"{status}: {url}")

print("\n" + "="*80)
print("Configuration test complete!")
print("="*80)
