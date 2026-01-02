from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import tempfile
import os
import shutil
import json
import zipfile
from typing import List
from app.services.narrative_video import process_media_with_voice, process_image_collection, generate_google_tts
import os
import shutil
import tempfile

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
    language: str = Form("fr-FR", description="Language code for TTS (e.g., en-US, fr-FR, es-ES)")
):
    """
    Generate narrative videos from PDF, images, or a collection of images and a script.
    Returns a ZIP file containing the generated video segments.
    
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
            results, logs = await process_media_with_voice(
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
            results, logs = await process_image_collection(
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
        
        # Schedule cleanup after response
        background_tasks.add_task(cleanup_temp_dir, temp_dir)
        
        return FileResponse(
            zip_path, 
            media_type="application/zip", 
            filename="narrative_videos.zip"
        )
            
    except Exception as e:
        # If something goes wrong, clean up immediately
        cleanup_temp_dir(temp_dir)
        raise HTTPException(status_code=500, detail=str(e))
