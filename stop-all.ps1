$ErrorActionPreference = 'SilentlyContinue'
$Runtime = 'D:\moodA\.runtime'

function Stop-PortProcess($Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen
    foreach ($connection in $connections) {
        $process = Get-Process -Id $connection.OwningProcess
        if ($process) {
            Stop-Process -Id $process.Id -Force
            Write-Host "Stopped process on port $Port (PID=$($process.Id))."
        }
    }
}

foreach ($name in @('frontend','python-agent','java-backend')) {
    $pidFile = Join-Path $Runtime "$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile | Select-Object -First 1)
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $processId -Force
            Write-Host "$name stopped (PID=$processId)."
        }
        Remove-Item $pidFile -Force
    }
}

# Also handle services started manually before the PID files existed.
Stop-PortProcess 5500
Stop-PortProcess 8081
Stop-PortProcess 8080

Write-Host 'Services started by the script are stopped. Databases and Redis are not stopped.'
