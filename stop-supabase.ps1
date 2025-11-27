# Stop all Supabase containers
Write-Host "Stopping all Supabase containers..." -ForegroundColor Yellow

$supabaseContainers = docker ps -a --filter "name=supabase" --format "{{.Names}}"

if ($supabaseContainers) {
    foreach ($container in $supabaseContainers) {
        Write-Host "Stopping and removing: $container" -ForegroundColor Cyan
        docker stop $container
        docker rm $container
    }
    Write-Host "All Supabase containers stopped and removed!" -ForegroundColor Green
} else {
    Write-Host "No Supabase containers found." -ForegroundColor Gray
}

# Optional: Remove Supabase networks
Write-Host "`nCleaning up Supabase networks..." -ForegroundColor Yellow
$supabaseNetworks = docker network ls --filter "name=supabase" --format "{{.Name}}"
if ($supabaseNetworks) {
    foreach ($network in $supabaseNetworks) {
        docker network rm $network 2>$null
        if ($?) {
            Write-Host "Removed network: $network" -ForegroundColor Cyan
        }
    }
}

Write-Host "`nDone!" -ForegroundColor Green
