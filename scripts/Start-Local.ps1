param(
    [int]$BackendPort = 18080,
    [int]$MlPort = 18000,
    [int]$PostgresPort = 15432,
    [string]$Database = 'meditron_final_test',
    [string]$DbUser = 'meditron',
    [string]$DbPassword = 'meditron-local-test',
    [string]$Java = '',
    [switch]$SkipPostgres
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null
if (!$Java) {
    if ($env:JAVA_HOME) { $Java = Join-Path $env:JAVA_HOME 'bin/java.exe' }
    elseif (Get-Command java -ErrorAction SilentlyContinue) { $Java = (Get-Command java).Source }
    elseif (Test-Path 'C:/Program Files/Java/jdk-25/bin/java.exe') { $Java = 'C:/Program Files/Java/jdk-25/bin/java.exe' }
    else { throw 'Install Java 21+ or pass -Java path/to/java.exe.' }
}
$pythonExe = Join-Path $projectRoot 'ml/.venv/Scripts/python.exe'
$jarPath = Join-Path $projectRoot 'backend/target/routing-0.0.1-SNAPSHOT.jar'
if (!(Test-Path $pythonExe) -or !(Test-Path $jarPath)) { throw 'Build backend and install ml/.venv first; see README.md.' }
$env:DB_URL = "jdbc:postgresql://127.0.0.1:$PostgresPort/$Database"
$env:DB_USER = $DbUser
$env:DB_PASSWORD = $DbPassword
$env:ML_SERVICE_URL = "http://127.0.0.1:$MlPort"
$env:BACKEND_URL = "http://127.0.0.1:$BackendPort"
$env:ML_DATABASE = Join-Path $localDir 'events.sqlite3'
$env:DEMO_SEED = 'false'
Remove-Item Env:ML_DICTIONARY -ErrorAction SilentlyContinue
if (!$SkipPostgres) {
    $pgCtl = Join-Path $localDir 'postgresql/pgsql/bin/pg_ctl.exe'
    $pgData = Join-Path $localDir 'pgdata'
    if (!(Test-Path $pgCtl) -or !(Test-Path (Join-Path $pgData 'PG_VERSION'))) {
        throw 'Portable PostgreSQL is not initialized. Use -SkipPostgres with your existing database, or see README.md.'
    }
    & $pgCtl -D $pgData status *> $null
    if ($LASTEXITCODE -ne 0) {
        & $pgCtl -D $pgData -l (Join-Path $localDir 'postgres.log') -o "-p $PostgresPort -h 127.0.0.1" -w start
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start.' }
    }
}
function Wait-Healthy([string]$Url) {
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try { $null = Invoke-RestMethod $Url -TimeoutSec 2; return }
        catch { Start-Sleep -Milliseconds 500 }
    }
    throw "Service not ready: $Url. See .local logs."
}
function Assert-ProjectProcess($Listeners, [string]$Expected) {
    foreach ($processId in ($Listeners.OwningProcess | Sort-Object -Unique)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
        $command = ([string]$process.CommandLine).Replace('\','/')
        $owned = $command.Contains($projectRoot.Replace('\','/'))
        if (!$owned -and $Expected -eq '-m app serve') {
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
            $parentCommand = ([string]$parent.CommandLine).Replace('\','/')
            $owned = $parent -and $parent.CreationDate -le $process.CreationDate -and $parentCommand.Contains($projectRoot.Replace('\','/') + '/ml/.venv/Scripts/python.exe') -and $parentCommand.Contains($Expected)
        }
        if (!$owned -or !$command.Contains($Expected)) {
            throw "Port is occupied by another process ($processId); choose different ports."
        }
    }
}
$existingBackend = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
if ($existingBackend) { Assert-ProjectProcess $existingBackend 'routing-0.0.1-SNAPSHOT.jar' }
if (!$existingBackend) {
    $backendProcess = Start-Process -FilePath $Java -ArgumentList @('-jar',('"' + $jarPath + '"'),"--server.port=$BackendPort",'--server.address=127.0.0.1') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'backend.stdout.log') -RedirectStandardError (Join-Path $localDir 'backend.stderr.log')
    $backendProcess.Id | Set-Content (Join-Path $localDir 'backend.pid')
}
Wait-Healthy "$env:BACKEND_URL/actuator/health"
$existingMl = Get-NetTCPConnection -LocalPort $MlPort -State Listen -ErrorAction SilentlyContinue
if ($existingMl) { Assert-ProjectProcess $existingMl '-m app serve' }
if (!$existingMl) {
    $mlProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','app','serve','--host','127.0.0.1','--port',"$MlPort",'--database',('"' + $env:ML_DATABASE + '"'),'--backend-url',$env:BACKEND_URL) -WorkingDirectory (Join-Path $projectRoot 'ml') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'ml.stdout.log') -RedirectStandardError (Join-Path $localDir 'ml.stderr.log')
    $mlProcess.Id | Set-Content (Join-Path $localDir 'ml.pid')
}
Wait-Healthy "http://127.0.0.1:$MlPort/health"
Write-Output "Backend: $env:BACKEND_URL/swagger-ui/index.html"
Write-Output "ML: http://127.0.0.1:$MlPort/docs"
