# Toolbox API

A comprehensive FastAPI service providing various utility tools for video processing, audio transcription, and audit time calculations.

## Features

- **Video Processing**: Extract the last frame from video files.
- **Audio Transcription**: Transcribe audio files using AssemblyAI with speaker detection.
- **Audit Calculations**: Calculate IFS Audit Time using automated browser interaction.
- **FSSC Extraction**: Extract structured data from FSSC Audit Report PDFs.

## Installation & Setup

### Prerequisites

- Docker and Docker Compose
- OR Python 3.9+ with Playwright installed

### Using Docker (Recommended)

1. Build and start the services:
   ```bash
   docker-compose up -d
   ```
2. The API will be available at `http://localhost:8000`.

### Manual Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Install Playwright browsers:
   ```bash
   playwright install chromium
   ```
3. Run the application:
   ```bash
   uvicorn app:app --reload
   ```

## API Documentation

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

### Endpoints

#### 1. General Info
Get a list of available endpoints.
- **URL**: `/`
- **Method**: `GET`
- **Example**:
  ```bash
  curl http://localhost:8000/
  ```

#### 2. Extract Last Frame
Extracts the final frame from a video file as a JPEG image.
- **URL**: `/last-frame`
- **Method**: `POST`
- **Body**: `multipart/form-data`
  - `file`: Video file (binary)
- **Example**:
  ```bash
  curl -X POST -F "file=@video.mp4" http://localhost:8000/last-frame --output last_frame.jpg
  ```

#### 3. Transcribe Audio
Transcribes an audio file using AssemblyAI.
- **URL**: `/transcribe`
- **Method**: `POST`
- **Query Parameters**:
  - `lang` (optional): Language code (default: "fr")
  - `format` (optional): Output format, "json" or "txt" (default: "json")
- **Body**: `multipart/form-data`
  - `file`: Audio file (wav, mp3, etc.)
- **Example**:
  ```bash
  curl -X POST -F "file=@recording.mp3" "http://localhost:8000/transcribe?lang=en&format=txt"
  ```

#### 4. Calculate Audit Time
Calculates the minimum audit duration for IFS standards.
- **URL**: `/audit-time`
- **Method**: `POST`
- **Body**: JSON
  ```json
  {
    "standard": "IFS Food 7",
    "employees": 50,
    "productScopes": ["1", "4"],
    "processingSteps": ["P1", "P4"]
  }
  ```
- **Example**:
  ```bash
  curl -X POST http://localhost:8000/audit-time \
       -H "Content-Type: application/json" \
       -d '{"standard": "IFS Food 7", "employees": 50, "productScopes": ["1"], "processingSteps": ["P1"]}'
  ```

#### 5. Extract FSSC Report Data
Extracts structured data from FSSC Audit Report PDFs.
- **URL**: `/extract/fssc`
- **Method**: `POST`
- **Query Parameters**:
  - `format` (optional): Output format, "zip" or "json" (default: "zip")
- **Body**: `multipart/form-data`
  - `file`: PDF file
- **Example**:
  ```bash
  # Download as ZIP containing JSON and Text
  curl -X POST -F "file=@report.pdf" http://localhost:8000/extract/fssc --output extraction.zip
  ```
