import uuid
import tempfile
import shutil
import io
import zipfile
import time
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import Response
from app.services.fssc_extractor import FSSCExtractorV2

router = APIRouter()

@router.post("/extract/fssc", tags=["FSSC"])
async def extract_fssc(file: UploadFile = File(...), format: str = "zip"):
    request_id = str(uuid.uuid4())[:8]
    
    # Create temp directory
    temp_dir = Path(tempfile.gettempdir()) / 'audit_extractor' / request_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Save uploaded file
        pdf_path = temp_dir / file.filename
        with open(pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # Extract
        extractor = FSSCExtractorV2(str(pdf_path))
        result = extractor.extract()
        
        # Save results locally in temp
        txt_path = temp_dir / 'extracted_text.txt'
        json_path = temp_dir / 'extracted_data.json'
        metadata_path = temp_dir / 'metadata.json'
        
        # Save text
        with open(txt_path, 'w', encoding='utf-8') as f:
            # We need to access the internal text extraction method or just re-extract
            # Since FSSCExtractorV2.extract() saves the text file as side effect to pdf_path.with_suffix('.txt')
            # Let's check where it saved it.
            # It saves to pdf_path.with_suffix('.txt')
            generated_txt_path = pdf_path.with_suffix('.txt')
            if generated_txt_path.exists():
                shutil.copy(generated_txt_path, txt_path)
            else:
                # Fallback if not saved
                f.write("Text extraction failed or file not found.")

        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        # Metadata
        metadata = {
            "request_id": request_id,
            "filename": file.filename,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "extraction_type": "FSSC 22000",
            "statistics": {
                "total_chapters": len(result['chapters']),
                "total_sections": sum(len(ch['sections']) for ch in result['chapters']),
                "expected_sections": 120
            }
        }
        with open(metadata_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        if format == "json":
            return {
                "success": True,
                "request_id": request_id,
                "metadata": metadata,
                "data": result
            }
        else:
            # Create ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                if txt_path.exists():
                    zip_file.write(txt_path, 'extracted_text.txt')
                if json_path.exists():
                    zip_file.write(json_path, 'extracted_data.json')
                if metadata_path.exists():
                    zip_file.write(metadata_path, 'metadata.json')
            
            zip_buffer.seek(0)
            return Response(
                content=zip_buffer.getvalue(),
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename=fssc_extraction_{request_id}.zip"}
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
