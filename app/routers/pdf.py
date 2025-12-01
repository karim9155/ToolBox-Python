from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
import tempfile
import os
import shutil
from app.utils.pdf_extractor import extract_images_from_pdf

router = APIRouter()

@router.post("/extract/pdf-images", tags=["PDF"])
async def extract_pdf_images(
    file: UploadFile = File(...),
    include_base64: bool = Query(True, description="Include base64 encoded images in the response")
):
    """
    Extract images and text from a PDF file.
    Returns a JSON object with extracted text and images.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Create a temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Save uploaded file
            temp_pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(temp_pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Run extraction
            # We don't need to save images to disk if we are returning base64, 
            # but the function supports it. Let's pass None for output_dir 
            # if we only want base64, or a temp path if we wanted to zip them.
            # For this endpoint, we'll just return the JSON with base64.
            
            result = extract_images_from_pdf(
                temp_pdf_path, 
                output_dir=None, 
                return_base64=include_base64
            )
            
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
            return JSONResponse(content=result)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
