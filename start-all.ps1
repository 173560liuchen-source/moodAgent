$ErrorActionPreference = 'Stop'

$Root = 'D:\moodA'
$Runtime = Join-Path $Root '.runtime'
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

$envFile = Join-Path $Root '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#][^=]*=' } | ForEach-Object {
        $pair = $_ -split '=', 2
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim().Trim('"'), 'Process')
    }
    Write-Host "Loaded $envFile"
}

function Test-Port($Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Start-ServiceProcess($Name, $FilePath, $Arguments, $WorkingDirectory, $Port) {
    if (Test-Port $Port) {
        Write-Host "$Name already running on port $Port; skipped."
        return
    }
    $stdout = Join-Path $Runtime "$Name.out.log"
    $stderr = Join-Path $Runtime "$Name.err.log"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content -Path (Join-Path $Runtime "$Name.pid") -Value $proc.Id
    Write-Host "$Name started, PID=$($proc.Id), port $Port."
}

Start-ServiceProcess 'frontend' 'python' @('-m','http.server','5500') "$Root\1" 5500

$python = Join-Path $Root 'moodappPython\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
Start-ServiceProcess 'python-agent' $python @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8081') "$Root\moodappPython" 8081

$jar = Get-ChildItem "$Root\moodapp\demo\target\*.jar" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $jar) {
    throw 'Java JAR not found. Run mvn package -DskipTests in D:\moodA\moodapp\demo first.'
}
$javaArgs = @('-Djava.io.tmpdir=' + (Join-Path $Runtime 'java-tmp'), '-jar', $jar.FullName)
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime 'java-tmp') | Out-Null
Start-ServiceProcess 'java-backend' 'java' $javaArgs "$Root\moodapp\demo" 8080

Write-Host ''
Write-Host 'Startup complete:'
Write-Host 'Frontend: http://127.0.0.1:5500/index.html'
Write-Host 'Java: http://127.0.0.1:8080/actuator/health'
Write-Host 'Python: http://127.0.0.1:8081/health'
