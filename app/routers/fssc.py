from fastapi import APIRouter, HTTPException, UploadFile, File
from app.services.fssc_service import extract_fssc

router = APIRouter()

@router.post('/extract/fssc')
async def extract_fssc_endpoint(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")
    try:
        contents = await file.read()
        # You may need to save the file or pass the bytes to extract_fssc
        result = extract_fssc(contents)
        return {'nodes': result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))