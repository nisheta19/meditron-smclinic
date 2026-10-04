param(
    [switch]$RepairDesktop,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dockerCommand = (Get-Command docker -ErrorAction Stop).Source
$desktopExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'

function Test-DockerEngine {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $dockerCommand
    $info.Arguments = 'info --format "{{.ServerVersion}}"'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        if (!$process.WaitForExit(5000)) {
            $process.Kill()
            $process.WaitForExit()
            return $false
        }
        return $process.ExitCode -eq 0
    } finally {
        $process.Dispose()
    }
}

Push-Location $projectRoot
try {
    if ($RepairDesktop) {
        $context = & $dockerCommand context show
        if ($LASTEXITCODE -ne 0 -or $context.Trim() -ne 'desktop-linux') {
            throw 'Repair is restricted to the local desktop-linux context.'
        }
        if (Test-DockerEngine) {
            $running = @(& $dockerCommand ps --format json | ForEach-Object { $_ | ConvertFrom-Json })
            if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect running containers.' }
            $foreign = @($running | Where-Object { $_.Labels -notmatch '(^|,)com.docker.compose.project=meditron-final(,|$)' })
            if ($foreign.Count) { throw 'Other projects have running containers. Stop them before repairing Desktop.' }
            & $dockerCommand compose stop
            if ($LASTEXITCODE -ne 0) { throw 'Cannot safely stop project containers.' }
        }

        # Only disposable, known Windows socket directories may be moved.
        $localData = [IO.Path]::GetFullPath($env:LOCALAPPDATA)
        $specs = @(
            @{ Path = Join-Path $localData 'Docker\run'; Names = @('dockerInference', 'userAnalyticsOtlpHttp.sock') },
            @{ Path = Join-Path $localData 'docker-secrets-engine'; Names = @('engine.sock') }
        )
        & $dockerCommand desktop stop --force --timeout 30
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop did not stop; no runtime paths changed.' }
        if (Get-Process -Name 'Docker Desktop','com.docker.backend' -ErrorAction SilentlyContinue) {
            throw 'Docker Desktop is still running; no runtime paths changed.'
        }
        # Shut down only Docker's VM so a pending WSL init cannot block its next boot.
        # The distribution is terminated, never unregistered; its disk is preserved.
        $wslDistributions = (& wsl.exe --list --quiet) -replace "`0", ''
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker WSL distribution.' }
        if (@($wslDistributions | ForEach-Object { $_.Trim() }) -contains 'docker-desktop') {
            $wslStopOutput = & wsl.exe --terminate docker-desktop 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Cannot stop Docker WSL distribution.' }
        }
        foreach ($spec in $specs) {
            if (!(Test-Path -LiteralPath $spec.Path)) { continue }
            $item = Get-Item -LiteralPath $spec.Path -Force
            if (!$item.PSIsContainer -or $item.FullName -ne $spec.Path -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Unexpected runtime directory: $($spec.Path)"
            }
            foreach ($child in @(Get-ChildItem -LiteralPath $spec.Path -Force)) {
                if ($child.PSIsContainer -or $child.Name -notin $spec.Names -or $child.Length -ne 0) {
                    throw "Unexpected runtime contents; preserved without changes: $($spec.Path)"
                }
            }
        }
        $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
        $backups = @()
        foreach ($spec in $specs) {
            if (Test-Path -LiteralPath $spec.Path) {
                $item = Get-Item -LiteralPath $spec.Path -Force
                $backupName = $item.Name + '.before-meditron-' + $stamp
                Rename-Item -LiteralPath $spec.Path -NewName $backupName
                $backups += @{ runtime = $spec.Path; backup = Join-Path $item.Parent.FullName $backupName }
            }
            [void](New-Item -ItemType Directory -Path $spec.Path -Force)
        }
        [void](New-Item -ItemType Directory -Path (Join-Path $projectRoot '.local') -Force)
        $backups | ConvertTo-Json | Set-Content (Join-Path $projectRoot ".local/docker-repair-$stamp.json") -Encoding utf8
        Write-Host 'Temporary socket directories renewed; backups kept. Docker volumes and settings unchanged.'
    }

    if (!(Test-DockerEngine)) {
        if (!(Test-Path -LiteralPath $desktopExe)) { throw "Docker Desktop not found: $desktopExe" }
        Start-Process -FilePath $desktopExe -WindowStyle Hidden
        Write-Host 'Waiting for Docker Engine...'
        $deadline = (Get-Date).AddSeconds(90)
        do {
            if (Test-DockerEngine) { break }
            if ((Get-Date) -ge $deadline) {
                throw 'Docker Engine did not start. For the known stale-socket error, rerun with -RepairDesktop.'
            }
            Start-Sleep -Seconds 2
        } while ($true)
    }
    $composeArgs = @('compose', 'up', '-d', '--wait', '--wait-timeout', '180')
    if (!$SkipBuild) { $composeArgs += '--build' }
    & $dockerCommand @composeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Inspect docker compose logs.' }
    & $dockerCommand compose ps
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read Compose state.' }
} finally {
    Pop-Location
}
