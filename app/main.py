from fastapi import FastAPI
from dotenv import load_dotenv
import os
import logging

# Load environment variables BEFORE importing routers/services
# (services read env vars at import time)
load_dotenv()

from app.routers import video, audio, audit, fssc, pdf, narrative, scraper

# Configure logging to show all details in console
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

app = FastAPI(title="Toolbox API", version="1.0")

app.include_router(video.router)
app.include_router(audio.router)
app.include_router(audit.router)
app.include_router(fssc.router)
app.include_router(pdf.router)
app.include_router(narrative.router)
app.include_router(scraper.router)


@app.get("/health", tags=["Health"])
def health_check():
    """
    Lightweight health check endpoint.
    Called by the TypeScript client (isScraplingAvailable) with a 2-second timeout.
    Must respond instantly — no browser launch, no heavy imports.
    """
    try:
        # Verify Scrapling is importable (catches missing library / broken venv)
        from scrapling import Fetcher as _ScraplingFetcher  # noqa: F401
        scrapling_ready = True
    except ImportError:
        scrapling_ready = False

    return {"status": "ok", "scrapling_ready": scrapling_ready}


@app.get("/")
def root():
    return {
        "POST /last-frame": "multipart form-data field 'file' -> image/jpeg",
        "POST /transcribe": "multipart form-data field 'file' -> json/text",
        "POST /audit-time": "json body -> audit duration",
        "POST /extract/fssc": "multipart form-data field 'file' -> json",
        "POST /extract/pdf-images": "multipart form-data field 'file' (.pdf/.docx/.doc/.pptx/.ppt) -> json (with base64 images)",
        "POST /generate-narrative": "multipart form-data field 'file' (PDF) + 'script' (JSON) -> zip (videos)",
        "POST /video-to-gif": "multipart form-data field 'file' (video) + optional query params (fps, width, max_duration) -> image/gif",
        # Scraper endpoints
        "POST /scrape/eurlex/search": "json {query, max_results} -> EUR-Lex search results",
        "GET /scrape/eurlex/document/{celex}": "EUR-Lex document by CELEX number",
        "POST /scrape/legifrance/search": "json {query, max_results} -> Legifrance search results (stealth)",
        "GET /scrape/legifrance/document/{doc_id}": "Legifrance document by ID (stealth)",
    }
