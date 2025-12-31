# Reconnect Medidok network share to M: drive
# This script must be run as Administrator

Write-Host "Removing existing M: drive mapping..." -ForegroundColor Yellow
try {
    net use M: /delete /yes 2>$null
    Start-Sleep -Seconds 1
} catch {
    Write-Host "No existing mapping to remove" -ForegroundColor Gray
}

Write-Host "Connecting to \\server\Medidok..." -ForegroundColor Yellow
$result = net use M: \\server\Medidok /user:Netadmin "opgekz(2019)" /persistent:yes

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Successfully connected M: drive!" -ForegroundColor Green
    Write-Host "`nTesting access..." -ForegroundColor Yellow
    $items = Get-ChildItem M:\ -ErrorAction SilentlyContinue
    if ($items) {
        Write-Host "✅ M: drive is accessible" -ForegroundColor Green
        Write-Host "`nContents of M:\:" -ForegroundColor Cyan
        $items | Select-Object -First 10 Name, Length, LastWriteTime | Format-Table
    } else {
        Write-Host "⚠️ M: drive connected but appears empty" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ Failed to connect M: drive" -ForegroundColor Red
    Write-Host "Error: $result" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ Ready to start Docker!" -ForegroundColor Green
Write-Host "Run: docker-compose up -d" -ForegroundColor Cyan
