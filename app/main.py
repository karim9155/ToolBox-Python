from fastapi import FastAPI
from app.routers import video, audio, audit, fssc

app = FastAPI(title="Toolbox API", version="1.0")

app.include_router(video.router)
app.include_router(audio.router)
app.include_router(audit.router)
app.include_router(fssc.router)

@app.get("/")
def root():
    return {
        "POST /last-frame": "multipart form-data field 'file' -> image/jpeg",
        "POST /transcribe": "multipart form-data field 'file' -> json/text",
        "POST /audit-time": "json body -> audit duration",
        "POST /extract/fssc": "multipart form-data field 'file' -> zip/json"
    }
