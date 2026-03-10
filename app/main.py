from fastapi import FastAPI
from app.routers import video, audio, audit, fssc, pdf, narrative, scraper
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Toolbox API", version="1.0")

app.include_router(video.router)
app.include_router(audio.router)
app.include_router(audit.router)
app.include_router(fssc.router)
app.include_router(pdf.router)
app.include_router(narrative.router)
app.include_router(scraper.router)

@app.get("/")
def root():
    return {
        "POST /last-frame": "multipart form-data field 'file' -> image/jpeg",
        "POST /transcribe": "multipart form-data field 'file' -> json/text",
        "POST /audit-time": "json body -> audit duration",
        "POST /extract/fssc": "multipart form-data field 'file' -> json",
        "POST /extract/pdf-images": "multipart form-data field 'file' -> json (with base64 images)",
        "POST /generate-narrative": "multipart form-data field 'file' (PDF) + 'script' (JSON) -> zip (videos)",
        # Scraper endpoints
        "POST /scrape/eurlex/search": "json {query, max_results} -> EUR-Lex search results",
        "GET /scrape/eurlex/document/{celex}": "EUR-Lex document by CELEX number",
        "POST /scrape/legifrance/search": "json {query, max_results} -> Legifrance search results (stealth)",
        "GET /scrape/legifrance/document/{doc_id}": "Legifrance document by ID (stealth)",
    }
