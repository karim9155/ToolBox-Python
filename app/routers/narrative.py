from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import tempfile
import os
import shutil
import json
import zipfile
from typing import List
from app.services.narrative_video import process_pdf_with_voice, generate_google_tts
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
    file: UploadFile = File(...),
    script: str = Form(..., description="JSON string containing the voice data script"),
    language: str = Form("fr-FR", description="Language code for TTS (e.g., en-US, fr-FR, es-ES)")
):
    """
    Generate narrative videos from a PDF and a script.
    Returns a ZIP file containing the generated video segments.
    
    The script should be a JSON array of objects with:
    - page_number: int
    - voice_over: str
    - slide_title: str (optional)
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        voice_data = json.loads(script)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON script")

    # Create a temporary directory for processing
    # We create it in a way that it persists until the file is sent, then we clean it up
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Save uploaded PDF
        pdf_path = os.path.join(temp_dir, "input.pdf")
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Process
        results, logs = await process_pdf_with_voice(
            pdf_path=pdf_path,
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
