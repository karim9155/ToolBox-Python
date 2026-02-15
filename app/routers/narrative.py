from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import os
import shutil
import json
import zipfile
import threading
import base64
import time
import traceback
from typing import List, Optional
from app.services.narrative_video import process_media_with_voice, process_image_collection, generate_google_tts
from app.utils.callback import (
    validate_callback_url,
    send_callback,
    register_job,
    update_job_status,
    get_job_status
)

router = APIRouter()

def cleanup_temp_dir(path: str):
    try:
        shutil.rmtree(path)
    except Exception as e:
        print(f"Error cleaning up {path}: {e}")

@router.get("/test-tts", tags=["Video"])
async def test_tts_endpoint():
    """
    Test endpoint to verify if Google TTS is working on the server.
    """
    logs = []
    logs.append("Testing Google Cloud TTS...")
    
    # 2. Try to generate audio
    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, "test.mp3")
    voice = "fr-FR-Neural2-B"
    text = "Ceci est un test de synthèse vocale Google."
    
    try:
        logs.append(f"Attempting to generate audio with {voice}...")
        await generate_google_tts(text, audio_path, voice_name=voice)
        
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logs.append("✅ Audio generated successfully.")
            # Clean up
            shutil.rmtree(temp_dir)
            return {"status": "success", "logs": logs}
        else:
            logs.append("❌ Audio file is empty or missing.")
            shutil.rmtree(temp_dir)
            return {"status": "failed", "logs": logs}
            
    except Exception as e:
        logs.append(f"❌ TTS Generation failed: {e}")
        shutil.rmtree(temp_dir)
        return {"status": "error", "logs": logs}

@router.post("/generate-narrative", tags=["Video"])
async def generate_narrative_video(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="PDF or image files (PDF, JPG, PNG, GIF)"),
    script: str = Form(..., description="JSON string containing the voice data script"),
    language: str = Form("fr-FR", description="Language code for TTS (e.g., en-US, fr-FR, es-ES)"),
    jobId: Optional[str] = Form(None, description="Unique job identifier for async callback workflow"),
    callbackUrl: Optional[str] = Form(None, description="URL to POST results when complete (enables async mode)"),
    callbackSecret: Optional[str] = Form(None, description="Secret for x-callback-secret header authentication"),
    documentId: Optional[str] = Form(None, description="Document identifier for tracking"),
    projectId: Optional[str] = Form(None, description="Project identifier for tracking")
):
    """
    Generate narrative videos from PDF, images, or a collection of images and a script.
    
    **Synchronous Mode** (default):
    Returns a ZIP file containing the generated video segments.
    
    **Async Mode** (when callbackUrl provided):
    Returns HTTP 202 immediately and POSTs results to callbackUrl when complete.
    
    Supported file types: PDF, JPG, JPEG, PNG, GIF
    
    You can provide:
    - A single PDF file
    - A single image file (JPG, PNG) or animated GIF
    - Multiple image files (will be processed in order)
    
    The script should be a JSON array of objects with:
    - page_number: int
    - voice_over: str
    - slide_title: str (optional)
    """
    # Validate file types
    allowed_extensions = ('.pdf', '.jpg', '.jpeg', '.png', '.gif')
    for file in files:
        if not file.filename.lower().endswith(allowed_extensions):
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' must be one of: {', '.join(allowed_extensions)}")

    try:
        voice_data = json.loads(script)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON script")

    # Check if async callback mode is enabled
    if callbackUrl:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 Async callback mode activated!")
        logger.info(f"   Callback URL: {callbackUrl[:60]}...")
        logger.info(f"{'='*80}\n")
        
        # Validate callback URL
        if not validate_callback_url(callbackUrl):
            raise HTTPException(status_code=400, detail="Invalid or disallowed callback URL")
        
        if not callbackSecret:
            raise HTTPException(status_code=400, detail="callbackSecret is required when using callbackUrl")
        
        # Generate job ID if not provided
        if not jobId:
            import uuid
            jobId = str(uuid.uuid4())
        
        logger.info(f"📝 Job ID: {jobId}")
        
        # Save uploaded files to temp directory
        temp_dir = tempfile.mkdtemp()
        saved_files = []
        
        try:
            for idx, file in enumerate(files):
                file_ext = os.path.splitext(file.filename)[1].lower()
                if len(files) == 1:
                    saved_path = os.path.join(temp_dir, f"input{file_ext}")
                else:
                    saved_path = os.path.join(temp_dir, f"image_{idx+1:03d}{file_ext}")
                
                with open(saved_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_files.append(saved_path)
        except Exception as e:
            cleanup_temp_dir(temp_dir)
            raise HTTPException(status_code=500, detail=f"Failed to save files: {str(e)}")
        
        # Register job
        register_job(jobId, {
            "callbackUrl": callbackUrl,
            "documentId": documentId,
            "projectId": projectId,
            "fileCount": len(files),
            "language": language
        })
        
        # Start background processing in thread
        thread = threading.Thread(
            target=_run_narrative_job_async,
            args=(jobId, callbackUrl, callbackSecret, temp_dir, saved_files, voice_data, language, documentId, projectId),
            daemon=True
        )
        thread.start()
        
        # Return immediately
        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "jobId": jobId,
                "message": "Video generation started",
                "estimatedTime": "10-15 minutes"
            }
        )
    
    # Synchronous mode (original behavior)
    # Create a temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Handle single file vs multiple files
        if len(files) == 1:
            # Single file - could be PDF, image, or animated GIF
            file = files[0]
            file_ext = os.path.splitext(file.filename)[1].lower()
            saved_file_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(saved_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            # Process single media file
            results, logs, tts_usage = await process_media_with_voice(
                media_path=saved_file_path,
                voice_data=voice_data,
                workdir=temp_dir,
                min_sections=3,
                language_code=language
            )
        else:
            # Multiple image files - save all and process as collection
            saved_files = []
            for idx, file in enumerate(files):
                file_ext = os.path.splitext(file.filename)[1].lower()
                saved_file_path = os.path.join(temp_dir, f"image_{idx+1:03d}{file_ext}")
                with open(saved_file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_files.append(saved_file_path)
            
            # Process multiple images as a collection
            results, logs, tts_usage = await process_image_collection(
                image_paths=saved_files,
                voice_data=voice_data,
                workdir=temp_dir,
                min_sections=3,
                language_code=language
            )

        
        if not results:
            raise HTTPException(status_code=500, detail="No videos were generated")
            
        # Zip the results
        zip_path = os.path.join(temp_dir, "narrative_videos.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for res in results:
                video_path = res["video_path"]
                arcname = os.path.basename(video_path)
                zipf.write(video_path, arcname)
            
            # Add log report
            report_path = os.path.join(temp_dir, "generation_report.txt")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(logs))
            zipf.write(report_path, "generation_report.txt")
            
            # Add TTS usage/pricing report
            pricing_path = os.path.join(temp_dir, "tts_pricing.json")
            with open(pricing_path, "w", encoding="utf-8") as f:
                json.dump(tts_usage, f, indent=2)
            zipf.write(pricing_path, "tts_pricing.json")
        
        # Schedule cleanup after response
        background_tasks.add_task(cleanup_temp_dir, temp_dir)
        
        # Add headers for immediate visibility
        headers = {
            "X-TTS-Cost-USD": str(tts_usage.get("total_cost_usd", 0)),
            "X-TTS-Characters": str(tts_usage.get("total_chars", 0)),
            "X-TTS-Voice": str(tts_usage.get("voice_name", "unknown"))
        }
        
        return FileResponse(
            zip_path, 
            media_type="application/zip", 
            filename="narrative_videos.zip",
            headers=headers
        )
            
    except Exception as e:
        # If something goes wrong, clean up immediately
        cleanup_temp_dir(temp_dir)
        raise HTTPException(status_code=500, detail=str(e))


def _run_narrative_job_async(
    job_id: str,
    callback_url: str,
    callback_secret: str,
    temp_dir: str,
    saved_files: List[str],
    voice_data: dict,
    language: str,
    document_id: Optional[str],
    project_id: Optional[str]
):
    """
    Background thread function to process narrative video generation and send callback.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"🎬 Starting background job: {job_id}")
    logger.info(f"   Files: {len(saved_files)}, Language: {language}")
    logger.info(f"   Document ID: {document_id}, Project ID: {project_id}")
    logger.info(f"{'='*80}\n")
    
    start_time = time.time()
    
    try:
        # Determine processing mode
        if len(saved_files) == 1:
            # Single file mode
            logger.info(f"📄 Processing single file: {saved_files[0]}")
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            logger.info(f"🎤 Starting TTS and video generation...")
            results, logs, tts_usage = loop.run_until_complete(
                process_media_with_voice(
                    media_path=saved_files[0],
                    voice_data=voice_data,
                    workdir=temp_dir,
                    min_sections=3,
                    language_code=language
                )
            )
            loop.close()
            logger.info(f"✅ Video generation complete: {len(results)} segments")
        else:
            # Multiple files mode
            logger.info(f"📄 Processing {len(saved_files)} files")
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            logger.info(f"🎤 Starting TTS and video generation...")
            results, logs, tts_usage = loop.run_until_complete(
                process_image_collection(
                    image_paths=saved_files,
                    voice_data=voice_data,
                    workdir=temp_dir,
                    min_sections=3,
                    language_code=language
                )
            )
            loop.close()
            logger.info(f"✅ Video generation complete: {len(results)} segments")
        
        if not results:
            raise Exception("No videos were generated")
        
        logger.info(f"\n📦 Uploading {len(results)} videos to Supabase...")
        
        # Calculate total duration
        total_duration = 0.0
        for res in results:
            if "duration" in res:
                total_duration += res["duration"]
        
        processing_time = time.time() - start_time
        
        logger.info(f"\n✅ Processing complete!")
        logger.info(f"   Total duration: {total_duration:.2f}s")
        logger.info(f"   Processing time: {processing_time:.2f}s")
        logger.info(f"   TTS cost: ${tts_usage.get('total_cost_usd', 0):.4f}")
        logger.info(f"   TTS characters: {tts_usage.get('total_chars', 0)}")
        
        # Determine environment from callback URL
        environment = "prod" if "myqateam.ai" in callback_url and "preprod" not in callback_url else "preprod"
        logger.info(f"   Target environment: {environment.upper()}")
        
        # Update job status
        update_job_status(job_id, "uploading", videoCount=len(results))
        
        # Import Supabase upload function
        from app.utils.supabase_storage import upload_video_to_supabase
        
        # Upload each video to Supabase and send lightweight callback
        successful_callbacks = 0
        failed_callbacks = 0
        
        for idx, res in enumerate(results):
            video_path = res["video_path"]
            filename = f"narrative_video_{idx}.mp4"
            
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"\n📹 Video {idx+1}/{len(results)}: {filename} ({file_size_mb:.2f} MB)")
            
            try:
                # Upload to Supabase
                upload_result = upload_video_to_supabase(
                    video_path=video_path,
                    document_id=document_id,
                    project_id=project_id,
                    filename=filename,
                    video_index=idx,
                    environment=environment
                )
                
                logger.info(f"   ✅ Uploaded to Supabase: {upload_result['storage_path']}")
                
                # Send lightweight callback (no video data!)
                callback_payload = {
                    "jobId": job_id,
                    "status": "video_ready",
                    "currentVideo": idx + 1,
                    "totalVideos": len(results),
                    "documentId": document_id,
                    "videoStoragePath": upload_result["storage_path"],
                    "videoRecordId": upload_result["record_id"]
                }
                
                if project_id:
                    callback_payload["projectId"] = project_id
                
                logger.info(f"   📞 Sending lightweight callback {idx+1}/{len(results)}...")
                
                success = send_callback(callback_url, callback_secret, callback_payload)
                
                if success:
                    successful_callbacks += 1
                    logger.info(f"   ✅ Callback sent successfully")
                else:
                    failed_callbacks += 1
                    logger.error(f"   ❌ Callback failed")
                    
            except Exception as e:
                failed_callbacks += 1
                logger.error(f"   ❌ Upload/callback failed: {e}")
        
        # Send final completion callback
        logger.info(f"\n📤 Sending final completion callback...")
        completion_payload = {
            "jobId": job_id,
            "status": "completed",
            "documentId": document_id,
            "metadata": {
                "totalVideos": len(results),
                "totalDuration": total_duration,
                "processingTime": round(processing_time, 2),
                "ttsCost": tts_usage.get("total_cost_usd", 0),
                "ttsCharacters": tts_usage.get("total_chars", 0),
                "voiceName": tts_usage.get("voice_name", "unknown"),
                "successfulUploads": successful_callbacks,
                "failedUploads": failed_callbacks
            }
        }
        
        if project_id:
            completion_payload["projectId"] = project_id
        
        success = send_callback(callback_url, callback_secret, completion_payload)
        
        if success and failed_callbacks == 0:
            logger.info(f"\n{'='*80}")
            logger.info(f"🎉 Job {job_id} completed successfully!")
            logger.info(f"   All {successful_callbacks} videos uploaded to Supabase")
            logger.info(f"{'='*80}\n")
            update_job_status(job_id, "completed")
        else:
            if failed_callbacks > 0:
                logger.warning(f"\n⚠️ Job {job_id} completed with {failed_callbacks} failed uploads")
                update_job_status(job_id, "completed_with_errors")
            else:
                logger.error(f"\n❌ Failed to send final completion callback")
                update_job_status(job_id, "callback_failed")
            logger.info(f"{'='*80}\n")
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"\n{'='*80}")
        logger.error(f"❌ Job {job_id} failed: {e}")
        logger.error(f"{'='*80}")
        logger.error(error_trace)
        
        processing_time = time.time() - start_time
        
        # Update job status
        update_job_status(job_id, "failed", error=str(e))
        
        # Send failure callback
        logger.info(f"\n📤 Sending failure callback...")
        callback_payload = {
            "jobId": job_id,
            "status": "failed",
            "error": str(e),
            "failedAt": "video_generation",
            "processingTime": round(processing_time, 2)
        }
        
        if document_id:
            callback_payload["documentId"] = document_id
        if project_id:
            callback_payload["projectId"] = project_id
        
        send_callback(callback_url, callback_secret, callback_payload)
        logger.info(f"{'='*80}\n")
    
    finally:
        # Always clean up temp directory
        cleanup_temp_dir(temp_dir)


@router.get("/narrative-job/{job_id}", tags=["Video"])
async def get_narrative_job_status(job_id: str):
    """
    Get the current status of a narrative video generation job.
    
    This endpoint allows polling for job status as a fallback if the callback fails.
    """
    job_status = get_job_status(job_id)
    
    if not job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    # Return sanitized status (don't expose callback URL/secret)
    return {
        "jobId": job_id,
        "status": job_status.get("status"),
        "createdAt": job_status.get("createdAt"),
        "updatedAt": job_status.get("updatedAt"),
        "fileCount": job_status.get("fileCount"),
        "videoCount": job_status.get("videoCount"),
        "language": job_status.get("language"),
        "documentId": job_status.get("documentId"),
        "projectId": job_status.get("projectId"),
        "error": job_status.get("error")
    }
