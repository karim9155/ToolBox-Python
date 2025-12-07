import tempfile
import requests
import time
import os
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import Response
from app.utils.common import mmss

router = APIRouter()

API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
if not API_KEY:
    print("Warning: ASSEMBLYAI_API_KEY not set. Transcription will fail.")
BASE = "https://api.assemblyai.com"
HEADERS = {"authorization": API_KEY}

@router.post("/transcribe", tags=["Audio"])
def transcribe(file: UploadFile = File(...), lang: str = "auto", format: str = "json"):
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
            "punctuate": True,
        }

        if lang and lang.lower() != "auto":
            payload["language_code"] = lang
        else:
            payload["language_detection"] = True
        
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
