from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import tempfile
import os
import shutil
import json
import zipfile
from typing import List
from app.services.narrative_video import process_pdf_with_voice

router = APIRouter()

def cleanup_temp_dir(path: str):
    try:
        shutil.rmtree(path)
    except Exception as e:
        print(f"Error cleaning up {path}: {e}")

@router.post("/generate-narrative", tags=["Video"])
async def generate_narrative_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    script: str = Form(..., description="JSON string containing the voice data script")
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
            min_sections=3
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
