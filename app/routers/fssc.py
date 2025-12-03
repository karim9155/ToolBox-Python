from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.fssc_service import FSSCService

router = APIRouter(prefix="/extract/fssc", tags=["fssc"])

# Initialize service (singleton-like)
fssc_service = FSSCService()

@router.post("/")
async def extract_fssc_report(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
    
    content = await file.read()
    result = fssc_service.process_file(content, file.filename)
    
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result["error"])
        
    return result["output"]
