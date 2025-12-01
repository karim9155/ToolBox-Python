FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /code

# Install system dependencies for OpenCV, ffmpeg, and Tesseract
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium for Playwright
RUN playwright install chromium

COPY . .

# Expose the port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
