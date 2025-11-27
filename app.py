import tempfile
import cv2
import requests
import time
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Union
from playwright.async_api import async_playwright
import zipfile
import io
import uuid
import shutil
from fssc_extractor import FSSCExtractorV2
from pathlib import Path

app = FastAPI(title="Toolbox API", version="1.0")

API_KEY = "c3e32648f5044e319c10eba6142bf280"
BASE = "https://api.assemblyai.com"
HEADERS = {"authorization": API_KEY}

def mmss(ms):
    s = int((ms or 0) / 1000)
    return f"{s//60:02d}:{s%60:02d}"

def extract_last_frame_bytes(data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(data)
        path = f.name

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ValueError("Cannot open video")

    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, n - 1)
        ok, frame = cap.read()
    else:
        ok, frame = False, None
        while True:
            r, fr = cap.read()
            if not r:
                break
            ok, frame = r, fr

    cap.release()

    if not ok or frame is None:
        raise ValueError("Failed to read last frame")

    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("Failed to encode frame")

    return buf.tobytes()

@app.get("/")
def root():
    return {
        "POST /last-frame": "multipart form-data field 'file' -> image/jpeg",
        "POST /transcribe": "multipart form-data field 'file' -> json/text",
        "POST /audit-time": "json body -> audit duration",
        "POST /extract/fssc": "multipart form-data field 'file' -> zip/json"
    }

@app.post("/last-frame")
async def last_frame(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return Response(content=extract_last_frame_bytes(data), media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/transcribe")
def transcribe(file: UploadFile = File(...), lang: str = "fr", format: str = "json"):
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        # Read the file content synchronously
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Upload
        with open(tmp_path, "rb") as audio:
            up = requests.post(f"{BASE}/v2/upload", headers=HEADERS, data=audio)
        
        up.raise_for_status()
        audio_url = up.json()["upload_url"]

        payload = {
            "audio_url": audio_url,
            "speaker_labels": True,
            "language_code": lang,
            "punctuate": True,
        }
        
        r = requests.post(f"{BASE}/v2/transcript", json=payload, headers=HEADERS)
        r.raise_for_status()
        tid = r.json()["id"]

        while True:
            g = requests.get(f"{BASE}/v2/transcript/{tid}", headers=HEADERS)
            g.raise_for_status()
            j = g.json()
            if j["status"] == "completed":
                break
            if j["status"] == "error":
                raise HTTPException(status_code=500, detail=j.get("error", "unknown"))
            time.sleep(3)

        utts = j.get("utterances") or []
        lines = [
            f"[{mmss(u.get('start'))}-{mmss(u.get('end'))}] Speaker {u.get('speaker','NA')}: {u.get('text','')}"
            for u in utts
        ]
        
        if format == "txt":
            return Response(content="\n".join(lines or [j.get("text","")]), media_type="text/plain")
        
        return {"lines": lines, "text": j.get("text",""), "utterances": utts}
        
    finally:
        # Clean up temp file
        try:
            import os
            os.unlink(tmp_path)
        except:
            pass

class AuditRequest(BaseModel):
    standard: str
    employees: int
    productScopes: List[Union[str, int]]
    processingSteps: List[str]

async def compute_audit_time_logic(standard, employees, product_scopes, processing_steps):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = await browser.new_page(viewport={'width': 1300, 'height': 900})
        
        try:
            await page.goto('https://time-calculator.ifs-certification.com/', wait_until='networkidle', timeout=120000)
            
            # Standard
            await page.wait_for_selector('button[aria-label="Open"]', timeout=30000)
            open_buttons = await page.query_selector_all('button[aria-label="Open"]')
            if open_buttons:
                await open_buttons[0].click()
            
            await page.wait_for_selector('li[role="option"]', timeout=20000)
            
            # Select standard
            found_std = await page.evaluate("""(wanted) => {
                const opts = Array.from(document.querySelectorAll('li[role="option"]'));
                const match = opts.find(li => (li.textContent || '').includes(wanted));
                if (match) { match.click(); return true; }
                return false;
            }""", standard)
            
            if not found_std:
                raise ValueError(f"Standard option not found: {standard}")
                
            # Employees
            await page.wait_for_selector('#numberOfEmployees', timeout=20000)
            await page.click('#numberOfEmployees', click_count=3)
            await page.type('#numberOfEmployees', str(employees), delay=10)
            
            # Helper for clicking labels
            async def click_by_label(val):
                val_str = str(val).strip()
                found = await page.evaluate("""(s) => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    let target = null;
                    
                    // Code match
                    if (/^\\d+$/.test(s)) {
                        target = labels.find(l => (l.textContent || '').trim().startsWith(s + ' '));
                    } else if (/^P\\d+$/i.test(s)) {
                        target = labels.find(l => (l.textContent || '').trim().toUpperCase().startsWith(s.toUpperCase() + ' '));
                    }
                    
                    // Fallback
                    if (!target) {
                        target = labels.find(l => (l.textContent || '').includes(s));
                    }
                    
                    if (target) {
                        target.scrollIntoView({ block: 'center' });
                        target.click();
                        return true;
                    }
                    return false;
                }""", val_str)
                
                if not found:
                    raise ValueError(f"Label not found: {val}")

            # Product Scopes
            for scope in product_scopes:
                await click_by_label(scope)
                
            # Processing Steps
            for step in processing_steps:
                await click_by_label(step)
                
            # Calculate
            await page.wait_for_function("""() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => /calculate/i.test(b.textContent || ''));
                return btn && !btn.hasAttribute('disabled');
            }""", timeout=30000)
            
            clicked_calc = await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => /calculate/i.test(b.textContent || ''));
                if (btn) {
                    btn.scrollIntoView({ block: 'center' });
                    btn.click();
                    return true;
                }
                return false;
            }""")
            
            if not clicked_calc:
                raise ValueError("Calculate button not found")
                
            # Result
            result = await page.wait_for_function("""() => {
                const p = Array.from(document.querySelectorAll('p'))
                    .find(el => /Minimum audit duration:/i.test(el.textContent || ''));
                const span = p?.querySelector('span');
                const txt = (span?.textContent || '').trim();
                if (!txt || txt.startsWith('-') || !/\\d+\\s*hours/i.test(txt)) return null;
                return txt;
            }""", timeout=60000)
            
            return await result.json_value()
            
        finally:
            await browser.close()

@app.post("/audit-time")
async def audit_time(request: AuditRequest):
    try:
        result = await compute_audit_time_logic(
            request.standard,
            request.employees,
            request.productScopes,
            request.processingSteps
        )
        return {"auditDuration": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract/fssc")
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
