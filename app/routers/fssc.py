
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.services.fssc_service import extract_fssc
import logging

logger = logging.getLogger("fssc_router")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

@router.post('/extract/fssc')
async def extract_fssc_endpoint(file: UploadFile = File(...)):
    if not file:
        logger.error("No file provided in request.")
        raise HTTPException(status_code=400, detail="Missing file")
    try:
        logger.info(f"Received file: {file.filename}, content_type: {file.content_type}")
        contents = await file.read()
        logger.info(f"File size: {len(contents)} bytes")
        result = extract_fssc(contents)
        logger.info(f"Extraction result: {len(result)} nodes returned.")
        return {'nodes': result}
    except Exception as e:
        logger.exception("Error during FSSC extraction")
        raise HTTPException(status_code=500, detail=str(e))