param([int]$BackendPort=18080, [int]$MlPort=18000, [switch]$KeepPostgres)
$ErrorActionPreference='Stop'
$projectRoot = (Split-Path -Parent $PSScriptRoot).Replace('\','/')
foreach ($port in @($BackendPort,$MlPort)) {
    $listeners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($processId in ($listeners.OwningProcess | Sort-Object -Unique)) {
        if (!$processId) { continue }
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
        # Never stop another application's process just because it occupies a port.
        $command=([string]$process.CommandLine).Replace('\','/')
        $owned = $command.Contains($projectRoot)
        if (!$owned -and $command.Contains('-m app serve')) {
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
            $parentCommand = ([string]$parent.CommandLine).Replace('\','/')
            $owned = $parent -and $parent.CreationDate -le $process.CreationDate -and $parentCommand.Contains($projectRoot + '/ml/.venv/Scripts/python.exe') -and $parentCommand.Contains('-m app serve')
        }
        if ($owned -and ($command.Contains('routing-0.0.1-SNAPSHOT.jar') -or $command.Contains('-m app serve'))) {
            $result = Invoke-CimMethod -InputObject $process -MethodName Terminate
            if ($result.ReturnValue -ne 0) { throw "Could not stop project process $processId" }
        } else { Write-Warning "Port $port belongs to another process; left running." }
    }
}
if (!$KeepPostgres) {
    $pgCtl=Join-Path $projectRoot '.local/postgresql/pgsql/bin/pg_ctl.exe'
    if (Test-Path $pgCtl) {
        & $pgCtl -D (Join-Path $projectRoot '.local/pgdata') status *> $null
        if ($LASTEXITCODE -eq 0) { & $pgCtl -D (Join-Path $projectRoot '.local/pgdata') -m fast -w stop }
    }
}
