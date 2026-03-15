from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
import tempfile
import os
import shutil
from app.utils.pdf_extractor import extract_images_from_pdf
from app.utils.document_converter import convert_document_to_pdf, ConversionError

router = APIRouter()

@router.post("/extract/pdf-images", tags=["PDF"])
async def extract_pdf_images(
    file: UploadFile = File(...),
    include_base64: bool = Query(True, description="Include base64 encoded images in the response")
):
    """
    Extract images and text from any document file.
    Non-PDF files are converted to PDF via LibreOffice before extraction.
    Returns a JSON object with extracted text and images.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = os.path.splitext(file.filename)[1].lower() or ".pdf"

    # Create a temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Save uploaded file
            temp_input_path = os.path.join(temp_dir, f"input{extension}")
            with open(temp_input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            extraction_pdf_path = temp_input_path
            if extension != ".pdf":
                extraction_pdf_path = convert_document_to_pdf(
                    temp_input_path,
                    temp_dir,
                    extension=extension,
                )
            
            # Run extraction
            # We don't need to save images to disk if we are returning base64, 
            # but the function supports it. Let's pass None for output_dir 
            # if we only want base64, or a temp path if we wanted to zip them.
            # For this endpoint, we'll just return the JSON with base64.
            
            result = extract_images_from_pdf(
                extraction_pdf_path,
                output_dir=None,
                return_base64=include_base64
            )

            if not result.get("success"):
                raise HTTPException(
                    status_code=422,
                    detail=result.get("error", "Failed to extract content from document")
                )

            return JSONResponse(content=result)

        except HTTPException:
            raise
        except ConversionError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
