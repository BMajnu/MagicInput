<#
.SYNOPSIS
  Start/stop/status/tail for background processes (detached) with logs and PID management.

.DESCRIPTION
  Designed for IDEs that only allow blocking terminal calls. This script starts a process in a detached
  manner and exits immediately, writing logs to files and the PID to a pidfile.

.USAGE EXAMPLES
  # Start a server
  .\scripts\background-run.ps1 start -FilePath "python" -ArgumentList "-m http.server 8000" -Name "http-server"

  # Stop by name (reads .\pids\http-server.pid)
  .\scripts\background-run.ps1 stop -Name "http-server"

  # Check status
  .\scripts\background-run.ps1 status -Name "http-server"

  # Tail latest stdout log for this name
  .\scripts\background-run.ps1 tail -Name "http-server" -Stream out

  # Tail specific file
  .\scripts\background-run.ps1 tail -OutLog ".\logs\http-server-20250101-120000.out"

.PARAMETERS
  -Action        start | stop | status | tail
  -FilePath      Executable path (e.g., python, node, npm). Required for start.
  -ArgumentList  Arguments string for the process. Optional.
  -Name          Logical name for PID/log files. If omitted, derived from FilePath.
  -Cwd           Working directory (default: current). Logs and pidfiles are under this path.
  -OutLog        Custom stdout log path. Default: <Cwd>\logs\<Name>-<timestamp>.out
  -ErrLog        Custom stderr log path. Default: <Cwd>\logs\<Name>-<timestamp>.err
  -PidFile       Custom pid file path. Default: <Cwd>\pids\<Name>.pid
  -Pid           Explicit PID for stop/status.
  -Port          For stop/status: detect PID from port (best effort).
  -Stream        For tail: out | err | both (default: out). For both, open 2 tails in 2 windows.
  -OutLog/-ErrLog For tail: specific file(s). If not provided, picks the most recent log for -Name.

  # Windsurf/Cascade-friendly readiness (optional, 'start' only)
  -WaitPort          Port number to wait until it's listening (e.g., 3000).
  -WaitHttp          HTTP URL to poll until 2xx/3xx (e.g., http://localhost:3000/health).
  -WaitLogPattern    Regex to look for in Out/Err logs indicating readiness.
  -ReadyTimeoutSec   Max seconds to wait for readiness (default: 20).
  -Url               URL hint to include in READY marker (defaults to http://localhost:<WaitPort> when set).
  -PrintWindsurfMarker  If set, always prints a concise 'WINDSURF:READY ...' line on success.
#>
param(
  [Parameter(Mandatory=$true)] [ValidateSet('start','stop','status','tail')] [string]$Action,
  [string]$FilePath,
  [string]$ArgumentList,
  [string]$Name,
  [string]$Cwd = (Get-Location).Path,
  [string]$OutLog,
  [string]$ErrLog,
  [string]$PidFile,
  [int]$Port,
  [int]$Pid,
  [ValidateSet('out','err','both')] [string]$Stream = 'out',
  [int]$WaitPort,
  [string]$WaitHttp,
  [string]$WaitLogPattern,
  [int]$ReadyTimeoutSec = 20,
  [string]$Url,
  [switch]$PrintWindsurfMarker
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Ensure-ParentDir([string]$Path) {
  if (-not [string]::IsNullOrWhiteSpace($Path)) {
    $dir = Split-Path -Path $Path -Parent
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
      New-Item -Path $dir -ItemType Directory -Force | Out-Null
    }
  }
}

function Get-NameFromFilePath([string]$fp) {
  if ([string]::IsNullOrWhiteSpace($fp)) { return 'process' }
  $leaf = Split-Path -Path $fp -Leaf
  return [System.IO.Path]::GetFileNameWithoutExtension($leaf)
}

function Get-DefaultPaths([string]$name, [string]$cwd) {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $logsDir = Join-Path $cwd 'logs'
  $pidsDir = Join-Path $cwd 'pids'
  $out = Join-Path $logsDir ("{0}-{1}.out" -f $name, $stamp)
  $err = Join-Path $logsDir ("{0}-{1}.err" -f $name, $stamp)
  $pid = Join-Path $pidsDir ("{0}.pid" -f $name)
  [pscustomobject]@{ OutLog=$out; ErrLog=$err; PidFile=$pid }
}

function Write-Result($obj) {
  # Print a compact summary and JSON for programmatic consumption.
  $summary = @()
  $obj.PSObject.Properties | ForEach-Object { $summary += ("{0}={1}" -f $_.Name, ($_.Value)) }
  Write-Output ($summary -join ' ')
  try { $obj | ConvertTo-Json -Depth 5 } catch { }
}

function Resolve-Log([string]$cwd, [string]$name, [ValidateSet('out','err')] [string]$stream) {
  $logsDir = Join-Path $cwd 'logs'
  if (-not (Test-Path -LiteralPath $logsDir)) { return $null }
  $pattern = if ($stream -eq 'out') { "{0}-*.out" -f $name } else { "{0}-*.err" -f $name }
  $files = Get-ChildItem -LiteralPath $logsDir -Filter $pattern -File | Sort-Object LastWriteTime -Descending
  if ($files -and $files.Count -gt 0) { return $files[0].FullName }
  return $null
}

function Test-HttpReady([string]$url) {
  try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($resp -and $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { return $true }
  } catch { }
  return $false
}

function Test-LogPattern([string]$pattern, [string]$outPath, [string]$errPath) {
  if ([string]::IsNullOrWhiteSpace($pattern)) { return $false }
  $opts = @{ ErrorAction = 'SilentlyContinue'; Quiet = $true }
  if ($outPath -and (Test-Path -LiteralPath $outPath)) {
    if (Select-String -Path $outPath -Pattern $pattern @opts) { return $true }
  }
  if ($errPath -and (Test-Path -LiteralPath $errPath)) {
    if (Select-String -Path $errPath -Pattern $pattern @opts) { return $true }
  }
  return $false
}

function Get-PidFromPort([int]$p) {
  try {
    $conn = Get-NetTCPConnection -ErrorAction Stop | Where-Object { $_.LocalPort -eq $p -and $_.State -in @('Listen','Established') } | Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
  } catch {
    # Fallback to netstat parsing
    $line = (& cmd /c "netstat -ano | findstr :$p" | Select-Object -First 1)
    if ($line) {
      $parts = -split ($line.Trim())
      if ($parts.Length -ge 5) { return [int]$parts[-1] }
    }
  }
  return $null
}

switch ($Action) {
  'start' {
    if ([string]::IsNullOrWhiteSpace($FilePath)) { throw "-FilePath is required for action 'start'" }
    if ([string]::IsNullOrWhiteSpace($Name)) { $Name = Get-NameFromFilePath $FilePath }

    $paths = Get-DefaultPaths -name $Name -cwd $Cwd
    if (-not $OutLog) { $OutLog = $paths.OutLog }
    if (-not $ErrLog) { $ErrLog = $paths.ErrLog }
    if (-not $PidFile) { $PidFile = $paths.PidFile }

    Ensure-ParentDir $OutLog
    Ensure-ParentDir $ErrLog
    Ensure-ParentDir $PidFile

    $proc = Start-Process -FilePath $FilePath `
                          -ArgumentList $ArgumentList `
                          -WorkingDirectory $Cwd `
                          -RedirectStandardOutput $OutLog `
                          -RedirectStandardError $ErrLog `
                          -WindowStyle Hidden `
                          -PassThru

    # Save PID
    Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding ascii

    # Optional readiness wait (Windsurf-friendly). Returns early if no wait flags provided.
    $didWait = $false
    $ready = $false
    if ($WaitPort -or $WaitHttp -or $WaitLogPattern) {
      $didWait = $true
      $deadline = (Get-Date).AddSeconds([math]::Max(1, $ReadyTimeoutSec))
      while ((Get-Date) -lt $deadline -and -not $ready) {
        $byPort = $false; $byHttp = $false; $byLog = $false
        if ($WaitPort) {
          try {
            $conns = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $WaitPort -and $_.State -eq 'Listen' }
            $byPort = ($conns -ne $null -and $conns.Count -ge 1)
          } catch { $byPort = ($null -ne (Get-PidFromPort -p $WaitPort)) }
        }
        if ($WaitHttp) { $byHttp = Test-HttpReady -url $WaitHttp }
        if ($WaitLogPattern) { $byLog = Test-LogPattern -pattern $WaitLogPattern -outPath $OutLog -errPath $ErrLog }
        if (($WaitPort -and $byPort) -or ($WaitHttp -and $byHttp) -or ($WaitLogPattern -and $byLog)) { $ready = $true; break }
        Start-Sleep -Milliseconds 250
      }
    }

    # Prepare URL hint
    $urlHint = $Url
    if (-not $urlHint -and $WaitPort) { $urlHint = "http://localhost:$WaitPort" }

    if ($ready -or -not $didWait) {
      if ($PrintWindsurfMarker -or $ready) {
        $__urlForMarker = if ($urlHint) { $urlHint } else { '' }
        Write-Output ("WINDSURF:READY name={0} pid={1} url={2} out={3} err={4}" -f $Name, $proc.Id, $__urlForMarker, $OutLog, $ErrLog)
      }
    }

    Write-Result ([pscustomobject]@{
      Action='start'; Name=$Name; Pid=$proc.Id; Cwd=$Cwd; OutLog=$OutLog; ErrLog=$ErrLog; PidFile=$PidFile; Waited=$didWait; Ready=$ready; Url=$urlHint
    })
  }

  'stop' {
    $targetPid = $null
    if ($Pid) { $targetPid = $Pid }
    elseif ($Port) { $targetPid = Get-PidFromPort -p $Port }
    elseif ($PidFile) { if (Test-Path -LiteralPath $PidFile) { $targetPid = [int](Get-Content -LiteralPath $PidFile -Raw) } }
    elseif ($Name) {
      $defaultPidFile = (Get-DefaultPaths -name $Name -cwd $Cwd).PidFile
      if (Test-Path -LiteralPath $defaultPidFile) { $targetPid = [int](Get-Content -LiteralPath $defaultPidFile -Raw) }
      else {
        # Last resort: by process name (may match multiple)
        $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like ("{0}*" -f $Name) }
        if ($procs) { $targetPid = $procs | Select-Object -ExpandProperty Id -First 1 }
      }
    }

    if (-not $targetPid) { throw "Could not determine PID to stop. Provide -Pid or -PidFile or -Name or -Port." }

    $killed = $false
    try {
      Stop-Process -Id $targetPid -Force -ErrorAction Stop
      $killed = $true
    } catch { }

    Write-Result ([pscustomobject]@{ Action='stop'; Pid=$targetPid; Stopped=$killed })
  }

  'status' {
    $pidToCheck = $null
    if ($Pid) { $pidToCheck = $Pid }
    elseif ($PidFile) { if (Test-Path -LiteralPath $PidFile) { $pidToCheck = [int](Get-Content -LiteralPath $PidFile -Raw) } }
    elseif ($Name) {
      $defaultPidFile = (Get-DefaultPaths -name $Name -cwd $Cwd).PidFile
      if (Test-Path -LiteralPath $defaultPidFile) { $pidToCheck = [int](Get-Content -LiteralPath $defaultPidFile -Raw) }
    }

    $running = $false
    if ($pidToCheck) {
      try { $p = Get-Process -Id $pidToCheck -ErrorAction Stop; $running = $true } catch { $running = $false }
    }

    $portPid = $null
    if ($Port) { $portPid = Get-PidFromPort -p $Port }

    Write-Result ([pscustomobject]@{
      Action='status'; Name=$Name; Pid=$pidToCheck; Running=$running; Port=$Port; PortPid=$portPid
    })
  }

  'tail' {
    $targetOut = $OutLog
    $targetErr = $ErrLog

    if ($Name -and -not $targetOut -and $Stream -in @('out','both')) { $targetOut = Resolve-Log -cwd $Cwd -name $Name -stream 'out' }
    if ($Name -and -not $targetErr -and $Stream -in @('err','both')) { $targetErr = Resolve-Log -cwd $Cwd -name $Name -stream 'err' }

    if ($Stream -eq 'both') {
      if (-not $targetOut -or -not $targetErr) { throw "For -Stream both, need -OutLog and -ErrLog or -Name to locate latest logs." }
      # Open two new windows to tail both logs
      Start-Process powershell -ArgumentList "-NoProfile -Command Get-Content -LiteralPath `"$targetOut`" -Wait -Tail 50"
      Start-Process powershell -ArgumentList "-NoProfile -Command Get-Content -LiteralPath `"$targetErr`" -Wait -Tail 50"
      Write-Result ([pscustomobject]@{ Action='tail'; OutLog=$targetOut; ErrLog=$targetErr; Mode='both' })
    } elseif ($Stream -eq 'out') {
      if (-not $targetOut) { throw "No stdout log found. Provide -OutLog or -Name." }
      Get-Content -LiteralPath $targetOut -Wait -Tail 50
    } else {
      if (-not $targetErr) { throw "No stderr log found. Provide -ErrLog or -Name." }
      Get-Content -LiteralPath $targetErr -Wait -Tail 50
    }
  }
}
