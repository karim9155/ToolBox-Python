import tempfile
import cv2
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import Response

router = APIRouter()

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

@router.post("/last-frame", tags=["Video"])
async def last_frame(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return Response(content=extract_last_frame_bytes(data), media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
