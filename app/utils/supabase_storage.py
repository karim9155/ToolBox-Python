"""
Supabase storage utilities for direct video upload.
"""
import os
import logging
import httpx
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Simple Supabase client using httpx
class SimpleSupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
    
    def upload_file(self, bucket: str, path: str, file_data: bytes, content_type: str = "video/mp4", upsert: bool = True):
        """Upload file to storage with upsert support"""
        url = f"{self.url}/storage/v1/object/{bucket}/{path}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": content_type,
            "x-upsert": "true" if upsert else "false"
        }
        response = httpx.post(url, headers=headers, content=file_data, timeout=300)
        
        if response.status_code not in [200, 201]:
            error_detail = response.text
            raise Exception(f"Storage upload failed ({response.status_code}): {error_detail}")
        
        return response.json()
    
    def create_signed_url(self, bucket: str, path: str, expires_in: int):
        """Create signed URL"""
        url = f"{self.url}/storage/v1/object/sign/{bucket}/{path}"
        response = httpx.post(
            url,
            headers=self.headers,
            json={"expiresIn": expires_in},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        # Return full URL
        signed_path = data.get("signedURL")
        return f"{self.url}/storage/v1{signed_path}"
    
    def insert_record(self, table: str, data: dict, upsert: bool = False):
        """Insert or upsert record into table"""
        url = f"{self.url}/rest/v1/{table}"
        headers = {**self.headers, "Prefer": "return=representation"}
        
        if upsert:
            # Use upsert with resolution=merge-duplicates
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        
        response = httpx.post(
            url,
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if isinstance(result, list) else result
    
    def delete_records(self, table: str, filters: dict):
        """Delete records from table"""
        url = f"{self.url}/rest/v1/{table}"
        # Build query string
        params = "&".join([f"{k}=eq.{v}" for k, v in filters.items()])
        response = httpx.delete(
            f"{url}?{params}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return True
    
    def delete_file(self, bucket: str, path: str):
        """Delete file from storage"""
        url = f"{self.url}/storage/v1/object/{bucket}/{path}"
        response = httpx.delete(
            url,
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return True

# Initialize Supabase clients
_supabase_local: Optional[SimpleSupabaseClient] = None
_supabase_preprod: Optional[SimpleSupabaseClient] = None
_supabase_prod: Optional[SimpleSupabaseClient] = None


def get_supabase_client(environment: str = None) -> SimpleSupabaseClient:
    """
    Get Supabase client for specified environment.
    
    Args:
        environment: 'preprod' or 'prod'. If None, uses DEPLOYMENT_ENV env var.
    
    Returns:
        SimpleSupabaseClient instance
    """
    global _supabase_local, _supabase_preprod, _supabase_prod
    
    if environment is None:
        environment = os.getenv("DEPLOYMENT_ENV", "preprod")
    
    environment = environment.lower()
    
    if environment == "local":
        if _supabase_local is None:
            url = os.getenv("SUPABASE_LOCAL_URL")
            key = os.getenv("SUPABASE_LOCAL_SERVICE_ROLE_KEY")
            
            if not url or not key:
                raise ValueError("Missing SUPABASE_LOCAL_URL or SUPABASE_LOCAL_SERVICE_ROLE_KEY")
            
            _supabase_local = SimpleSupabaseClient(url, key)
            logger.info(f"✅ Connected to Supabase LOCAL: {url}")
        
        return _supabase_local
    
    elif environment == "preprod":
        if _supabase_preprod is None:
            url = os.getenv("SUPABASE_PREPROD_URL")
            key = os.getenv("SUPABASE_PREPROD_SERVICE_ROLE_KEY")
            
            if not url or not key:
                raise ValueError("Missing SUPABASE_PREPROD_URL or SUPABASE_PREPROD_SERVICE_ROLE_KEY")
            
            _supabase_preprod = SimpleSupabaseClient(url, key)
            logger.info(f"✅ Connected to Supabase PREPROD: {url}")
        
        return _supabase_preprod
    
    elif environment == "prod":
        if _supabase_prod is None:
            url = os.getenv("SUPABASE_PROD_URL")
            key = os.getenv("SUPABASE_PROD_SERVICE_ROLE_KEY")
            
            if not url or not key:
                raise ValueError("Missing SUPABASE_PROD_URL or SUPABASE_PROD_SERVICE_ROLE_KEY")
            
            _supabase_prod = SimpleSupabaseClient(url, key)
            logger.info(f"✅ Connected to Supabase PROD: {url}")
        
        return _supabase_prod
    
    else:
        raise ValueError(f"Invalid environment: {environment}. Must be 'local', 'preprod' or 'prod'")


def upload_video_to_supabase(
    video_path: str,
    document_id: str,
    project_id: Optional[str],
    filename: str,
    video_index: int,
    environment: str = None
) -> Dict[str, str]:
    """
    Upload video directly to Supabase storage and insert record.
    
    Args:
        video_path: Local path to video file
        document_id: Document UUID
        project_id: Project UUID (optional)
        filename: Target filename (e.g., "narrative_video_0.mp4")
        video_index: Video sequence number (0, 1, 2, ...)
        environment: 'preprod' or 'prod'
    
    Returns:
        Dict with storage_path, signed_url, record_id
    """
    supabase = get_supabase_client(environment)
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "videos")
    expiry = int(os.getenv("SUPABASE_SIGNED_URL_EXPIRY", "604800"))
    
    # Construct storage path
    storage_path = f"generated-videos/{document_id}/{filename}"
    
    logger.info(f"📤 Uploading video to Supabase ({environment})...")
    logger.info(f"   Bucket: {bucket}")
    logger.info(f"   Path: {storage_path}")
    
    try:
        # 1. Upload video file
        with open(video_path, "rb") as f:
            video_bytes = f.read()
        
        file_size_mb = len(video_bytes) / (1024 * 1024)
        logger.info(f"   Size: {file_size_mb:.2f} MB")
        
        supabase.upload_file(
            bucket=bucket,
            path=storage_path,
            file_data=video_bytes,
            content_type="video/mp4"
        )
        
        logger.info(f"   ✅ Upload successful")
        
        # 2. Generate signed URL
        signed_url = supabase.create_signed_url(
            bucket=bucket,
            path=storage_path,
            expires_in=expiry
        )
        
        logger.info(f"   ✅ Signed URL generated (expires in {expiry//86400} days)")
        
        # 3. Insert record into narrative_videos table
        record_data = {
            "document_id": document_id,
            "video_index": video_index,
            "filename": filename,
            "storage_path": storage_path,
            "supabase_url": signed_url
        }
        
        if project_id:
            record_data["project_id"] = project_id
        
        # Use upsert to handle re-uploads gracefully
        record = supabase.insert_record("narrative_videos", record_data, upsert=True)
        
        record_id = record["id"]
        logger.info(f"   ✅ Database record created: {record_id}")
        
        return {
            "storage_path": storage_path,
            "signed_url": signed_url,
            "record_id": record_id
        }
        
    except Exception as e:
        logger.error(f"   ❌ Supabase upload failed: {e}")
        raise


def delete_video_from_supabase(
    document_id: str,
    video_index: int = None,
    environment: str = None
) -> bool:
    """
    Delete video(s) from Supabase storage and database.
    
    Args:
        document_id: Document UUID
        video_index: Specific video index to delete (None = delete all)
        environment: 'preprod' or 'prod'
    
    Returns:
        True if successful
    """
    supabase = get_supabase_client(environment)
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "videos")
    
    try:
        # 1. Delete from database
        filters = {"document_id": document_id}
        if video_index is not None:
            filters["video_index"] = video_index
        
        supabase.delete_records("narrative_videos", filters)
        
        # 2. Delete from storage
        if video_index is not None:
            # Delete specific video
            storage_path = f"generated-videos/{document_id}/narrative_video_{video_index}.mp4"
            supabase.delete_file(bucket, storage_path)
        else:
            # Delete entire folder - would need to list files first
            # For now, just delete database records
            pass
        
        logger.info(f"✅ Deleted videos for document {document_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to delete videos: {e}")
        return False
