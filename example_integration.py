"""
Example integration: How to call the async /generate-narrative endpoint
from your main application and handle callbacks.

This is a minimal example showing the client-side integration.
"""
import requests
import uuid
import json
from typing import Optional


class NarrativeVideoClient:
    """Client for interacting with the ToolBox narrative video API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_narrative_sync(
        self,
        files: list,
        script: list,
        language: str = "fr-FR"
    ) -> bytes:
        """
        Generate narrative video synchronously (original behavior).
        
        Args:
            files: List of tuples (filename, file_bytes, mimetype)
            script: List of dicts with page_number, voice_over, slide_title
            language: Language code for TTS
            
        Returns:
            ZIP file bytes containing generated videos
        """
        # Prepare files for multipart upload
        files_data = {
            'files': [
                (name, content, mimetype) 
                for name, content, mimetype in files
            ]
        }
        
        data = {
            'script': json.dumps(script),
            'language': language
        }
        
        response = requests.post(
            f"{self.base_url}/api/generate-narrative",
            files=files_data,
            data=data,
            timeout=600  # 10 minutes
        )
        
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f"Video generation failed: {response.status_code} {response.text}")
    
    def generate_narrative_async(
        self,
        files: list,
        script: list,
        callback_url: str,
        callback_secret: str,
        language: str = "fr-FR",
        job_id: Optional[str] = None,
        document_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> dict:
        """
        Generate narrative video asynchronously with callback.
        
        Args:
            files: List of tuples (filename, file_bytes, mimetype)
            script: List of dicts with page_number, voice_over, slide_title
            callback_url: URL to POST results when complete
            callback_secret: Secret for authentication
            language: Language code for TTS
            job_id: Optional job identifier (generated if not provided)
            document_id: Optional document identifier for tracking
            project_id: Optional project identifier for tracking
            
        Returns:
            Dict with jobId, message, estimatedTime
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        # Prepare files for multipart upload
        files_data = {
            'files': [
                (name, content, mimetype) 
                for name, content, mimetype in files
            ]
        }
        
        data = {
            'script': json.dumps(script),
            'language': language,
            'jobId': job_id,
            'callbackUrl': callback_url,
            'callbackSecret': callback_secret
        }
        
        if document_id:
            data['documentId'] = document_id
        if project_id:
            data['projectId'] = project_id
        
        response = requests.post(
            f"{self.base_url}/api/generate-narrative",
            files=files_data,
            data=data,
            timeout=30  # Should return immediately
        )
        
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"Failed to start job: {response.status_code} {response.text}")
    
    def get_job_status(self, job_id: str) -> dict:
        """
        Poll job status (fallback if callback fails).
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job status dict
        """
        response = requests.get(f"{self.base_url}/api/narrative-job/{job_id}")
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise Exception(f"Job {job_id} not found")
        else:
            raise Exception(f"Failed to get status: {response.status_code} {response.text}")


# ============================================================================
# Example Usage
# ============================================================================

def example_sync_usage():
    """Example: Synchronous video generation (blocks until complete)."""
    client = NarrativeVideoClient(base_url="http://localhost:8000")
    
    # Prepare files
    with open('slide1.png', 'rb') as f:
        files = [('slide1.png', f.read(), 'image/png')]
    
    # Prepare script
    script = [
        {
            "page_number": 1,
            "voice_over": "Bonjour, ceci est une présentation automatisée.",
            "slide_title": "Introduction"
        }
    ]
    
    # Generate video (blocks)
    print("Generating video synchronously...")
    zip_bytes = client.generate_narrative_sync(
        files=files,
        script=script,
        language="fr-FR"
    )
    
    # Save ZIP
    with open('output_videos.zip', 'wb') as f:
        f.write(zip_bytes)
    
    print("✅ Videos saved to output_videos.zip")


def example_async_usage():
    """Example: Asynchronous video generation with callback."""
    client = NarrativeVideoClient(base_url="http://localhost:8000")
    
    # Prepare files
    with open('slide1.png', 'rb') as f:
        files = [('slide1.png', f.read(), 'image/png')]
    
    # Prepare script
    script = [
        {
            "page_number": 1,
            "voice_over": "Cette vidéo est générée en arrière-plan.",
            "slide_title": "Async Generation"
        }
    ]
    
    # Start async generation
    print("Starting async video generation...")
    result = client.generate_narrative_async(
        files=files,
        script=script,
        callback_url="https://yourdomain.com/api/video-callback",
        callback_secret="your-secure-secret-here",
        document_id="doc-12345",
        project_id="project-67890"
    )
    
    job_id = result["jobId"]
    print(f"✅ Job started: {job_id}")
    print(f"   Estimated time: {result['estimatedTime']}")
    
    # Optional: Poll status as fallback
    import time
    for i in range(30):  # Poll for up to 5 minutes
        time.sleep(10)
        status = client.get_job_status(job_id)
        print(f"   Status: {status['status']}")
        
        if status['status'] in ['completed', 'failed', 'callback_failed']:
            break
    
    print("✅ Job complete - callback should have been sent")


def example_callback_handler():
    """
    Example: FastAPI callback endpoint in your main application.
    
    Add this to your main application to receive video generation results.
    """
    from fastapi import APIRouter, Request, HTTPException
    import base64
    
    router = APIRouter()
    
    @router.post("/api/video-callback")
    async def handle_video_callback(request: Request):
        """Receive video generation callbacks from ToolBox."""
        
        # 1. Verify secret
        secret = request.headers.get("x-callback-secret")
        expected_secret = "your-secure-secret-here"  # From env var in production
        
        if secret != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid callback secret")
        
        # 2. Parse callback data
        data = await request.json()
        job_id = data["jobId"]
        status = data["status"]
        document_id = data.get("documentId")
        project_id = data.get("projectId")
        
        # 3. Handle success
        if status == "completed":
            videos = data["videos"]
            metadata = data["metadata"]
            
            print(f"✅ Job {job_id} completed:")
            print(f"   - {metadata['videoCount']} videos")
            print(f"   - Processing time: {metadata['processingTime']}s")
            print(f"   - TTS cost: ${metadata['ttsCost']}")
            
            # Save videos to storage (S3, local filesystem, etc.)
            for video in videos:
                filename = video["filename"]
                video_bytes = base64.b64decode(video["data"])
                
                # Example: Save to local filesystem
                save_path = f"/storage/videos/{document_id}/{filename}"
                with open(save_path, "wb") as f:
                    f.write(video_bytes)
                
                print(f"   - Saved {filename} ({len(video_bytes)} bytes)")
            
            # Update database
            # db.update_document(document_id, status="video_ready", videos=videos)
            
            # Notify user (email, websocket, etc.)
            # notify_user(document_id, "Your videos are ready!")
            
        # 4. Handle failure
        elif status == "failed":
            error = data["error"]
            failed_at = data.get("failedAt")
            
            print(f"❌ Job {job_id} failed:")
            print(f"   - Error: {error}")
            print(f"   - Failed at: {failed_at}")
            
            # Update database
            # db.update_document(document_id, status="video_failed", error=error)
            
            # Notify user
            # notify_user(document_id, f"Video generation failed: {error}")
        
        # 5. Always return 200 (otherwise ToolBox will retry)
        return {"success": True}


if __name__ == "__main__":
    print("Narrative Video API Client Examples")
    print("=" * 60)
    
    # Run sync example
    # example_sync_usage()
    
    # Run async example
    # example_async_usage()
    
    print("\nSee function docstrings for usage details")
