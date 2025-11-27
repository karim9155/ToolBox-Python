# Build and push Docker image to Docker Hub
$USERNAME = "khldwbara"
$IMAGE_NAME = "toolbox-api"
$TAG = "latest"
$FULL_IMAGE = "${USERNAME}/${IMAGE_NAME}:${TAG}"

Write-Host "Building Docker image: $FULL_IMAGE" -ForegroundColor Cyan
docker build -t $FULL_IMAGE .

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "`nPushing to Docker Hub..." -ForegroundColor Cyan
    docker push $FULL_IMAGE

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nSuccess! Image pushed to Docker Hub." -ForegroundColor Green
        Write-Host "`nYour friend can pull and run it with:" -ForegroundColor Yellow
        Write-Host "  docker pull $FULL_IMAGE" -ForegroundColor White
        Write-Host "  docker run -d -p 9000:8000 --name toolbox-api $FULL_IMAGE" -ForegroundColor White
    } else {
        Write-Host "`nPush failed. Make sure you're logged in:" -ForegroundColor Red
        Write-Host "  docker login" -ForegroundColor White
    }
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}
