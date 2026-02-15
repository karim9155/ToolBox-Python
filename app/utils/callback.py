"""
Callback utilities for async job completion notifications.
"""
import os
import time
import logging
import requests
import threading
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# In-memory job status tracking
JOB_STATUS: Dict[str, Dict[str, Any]] = {}
JOB_STATUS_LOCK = threading.Lock()

# Environment configuration
CALLBACK_TIMEOUT = int(os.getenv("CALLBACK_TIMEOUT", "30"))
MAX_CALLBACK_RETRIES = int(os.getenv("MAX_CALLBACK_RETRIES", "3"))
ALLOWED_CALLBACK_DOMAINS = os.getenv("ALLOWED_CALLBACK_DOMAINS", "")
TOOLBOX_CALLBACK_SECRET = os.getenv("TOOLBOX_CALLBACK_SECRET", "")


def validate_callback_url(url: str) -> bool:
    """
    Validate callback URL to prevent SSRF attacks.
    
    Args:
        url: The callback URL to validate
        
    Returns:
        True if URL is valid, False otherwise
    """
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ["http", "https"]:
            logger.warning(f"❌ Invalid callback URL scheme: {parsed.scheme}")
            return False
        
        # Allow localhost for development
        if parsed.hostname in ["localhost", "127.0.0.1", "::1"]:
            return True
        
        # Check allowed domains if configured
        if ALLOWED_CALLBACK_DOMAINS:
            allowed = [d.strip() for d in ALLOWED_CALLBACK_DOMAINS.split(",")]
            if not any(parsed.hostname.endswith(domain) for domain in allowed):
                logger.warning(f"❌ Callback domain not allowed: {parsed.hostname}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error validating callback URL: {e}")
        return False


def send_callback(
    callback_url: str,
    callback_secret: Optional[str] = None,
    payload: Dict[str, Any] = None,
    max_retries: Optional[int] = None
) -> bool:
    """
    Send callback POST request with retry logic and exponential backoff.
    
    Args:
        callback_url: The URL to POST to
        callback_secret: Secret for x-callback-secret header (uses TOOLBOX_CALLBACK_SECRET env if None)
        payload: JSON payload to send
        max_retries: Maximum retry attempts (defaults to MAX_CALLBACK_RETRIES)
        
    Returns:
        True if callback succeeded, False otherwise
    """
    if max_retries is None:
        max_retries = MAX_CALLBACK_RETRIES
    
    # Use environment variable if callback_secret not provided
    secret = callback_secret or TOOLBOX_CALLBACK_SECRET
    if not secret:
        logger.error("❌ No callback secret provided and TOOLBOX_CALLBACK_SECRET not set")
        return False
    
    headers = {
        "Content-Type": "application/json",
        "x-callback-secret": secret
    }
    
    retry_delays = [1, 5, 15]  # Exponential backoff: 1s, 5s, 15s
    
    for attempt in range(max_retries):
        try:
            logger.info(f"📤 Sending callback to {callback_url} (attempt {attempt + 1}/{max_retries})")
            logger.info(f"   Job ID: {payload.get('jobId')}, Status: {payload.get('status')}")
            if payload.get('status') == 'completed':
                logger.info(f"   Videos: {len(payload.get('videos', []))}, Processing time: {payload.get('metadata', {}).get('processingTime')}s")
            
            response = requests.post(
                callback_url,
                headers=headers,
                json=payload,
                timeout=CALLBACK_TIMEOUT
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Callback successful: {response.status_code}")
                logger.info(f"   Response: {response.text[:100]}")
                return True
            else:
                logger.warning(f"⚠️ Callback failed: {response.status_code}")
                logger.warning(f"   Response: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Callback timeout after {CALLBACK_TIMEOUT}s")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Callback request error: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected callback error: {e}")
        
        # Retry with exponential backoff (except on last attempt)
        if attempt < max_retries - 1:
            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
            logger.info(f"🔄 Retrying in {delay}s...")
            time.sleep(delay)
    
    logger.error(f"❌ Callback failed after {max_retries} attempts")
    return False


def register_job(job_id: str, metadata: Dict[str, Any]) -> None:
    """
    Register a new job in the status tracker.
    
    Args:
        job_id: Unique job identifier
        metadata: Additional job metadata (callback URL, file count, etc.)
    """
    with JOB_STATUS_LOCK:
        JOB_STATUS[job_id] = {
            "status": "processing",
            "createdAt": time.time(),
            "updatedAt": time.time(),
            **metadata
        }
        logger.info(f"📝 Registered job: {job_id}")
        logger.info(f"   Files: {metadata.get('fileCount')}, Language: {metadata.get('language')}")
        logger.info(f"   Callback URL: {metadata.get('callbackUrl')[:50]}...")


def update_job_status(job_id: str, status: str, **kwargs) -> None:
    """
    Update job status in the tracker.
    
    Args:
        job_id: Job identifier
        status: New status (processing, completed, failed)
        **kwargs: Additional fields to update
    """
    with JOB_STATUS_LOCK:
        if job_id in JOB_STATUS:
            JOB_STATUS[job_id].update({
                "status": status,
                "updatedAt": time.time(),
                **kwargs
            })
            logger.info(f"📝 Updated job {job_id}: {status}")


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current status of a job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job status dict or None if not found
    """
    with JOB_STATUS_LOCK:
        return JOB_STATUS.get(job_id)


def cleanup_old_jobs(max_age_seconds: int = 3600) -> None:
    """
    Remove old completed/failed jobs from memory.
    
    Args:
        max_age_seconds: Maximum age to keep jobs (default 1 hour)
    """
    with JOB_STATUS_LOCK:
        current_time = time.time()
        to_remove = [
            job_id for job_id, job in JOB_STATUS.items()
            if job["status"] in ["completed", "failed"] 
            and (current_time - job["updatedAt"]) > max_age_seconds
        ]
        for job_id in to_remove:
            del JOB_STATUS[job_id]
            logger.info(f"🗑️ Cleaned up old job: {job_id}")
