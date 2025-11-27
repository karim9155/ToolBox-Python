# Docker Build and Push Instructions

## For You (Building and Pushing)

### 1. Login to Docker Hub
```powershell
docker login
```
Enter your Docker Hub credentials when prompted.

### 2. Build and Push
```powershell
.\build-and-push.ps1
```

Or manually:
```powershell
docker build -t khldwbara/toolbox-api:latest .
docker push khldwbara/toolbox-api:latest
```

### 3. Run locally from your image
```powershell
docker run -d -p 8000:8000 --name last-frame-api khldwbara/last-frame-api:latest
```

---

## For Your Friend (Pulling and Running)

### Pull and run the image
```bash
docker pull khldwbara/last-frame-api:latest
docker run -d -p 9000:8000 --name last-frame-api khldwbara/last-frame-api:latest
```

### Or use docker-compose
```bash
# Copy the docker-compose.yml file, then:
docker-compose up -d
```

### Access the API
- API: http://localhost:9000
- Docs: http://localhost:9000/docs

### Test endpoint
```bash
curl -X POST -F "file=@video.mp4" http://localhost:9000/last-frame --output last_frame.jpg
```

---

## Image Details
- **Image**: `khldwbara/last-frame-api:latest`
- **Port**: 9000 (mapped from internal 8000)
- **Endpoints**:
  - `GET /` - API info
  - `POST /last-frame` - Extract last frame from video
