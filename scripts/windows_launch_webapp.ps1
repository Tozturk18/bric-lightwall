param(
  [string]$RepoDir = "",
  [string]$Interface = "Ethernet",
  [string]$WebHost = "0.0.0.0",
  [int]$WebPort = 8080,
  [string]$Python = "",
  [string]$LogDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoDir) {
  $RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
  $RepoDir = (Resolve-Path $RepoDir).Path
}

if (-not $LogDir) {
  $LogDir = Join-Path $RepoDir "logs"
}
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$logFile = Join-Path $LogDir "webapp.log"

function Write-LogLine {
  param([string]$Message)
  $timestamp = Get-Date -Format o
  Add-Content -Path $logFile -Encoding UTF8 -Value "$timestamp $Message"
}

function Resolve-PythonCommand {
  param([string]$RequestedPython)

  if ($RequestedPython) {
    return @($RequestedPython)
  }

  $venvPython = Join-Path $RepoDir ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    return @($venvPython)
  }

  foreach ($candidate in @("python3", "python")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
      return @($command.Source)
    }
  }

  $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    return @($pyLauncher.Source, "-3")
  }

  throw "Could not find Python. Create .venv or pass -Python C:\Path\To\python.exe."
}

$pythonCommand = @(Resolve-PythonCommand $Python)
$pythonExe = $pythonCommand[0]
$pythonPrefixArgs = @()
if ($pythonCommand.Count -gt 1) {
  $pythonPrefixArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
}

$appArgs = @(
  "tools/webapp/app.py",
  "--interface", $Interface,
  "--web-host", $WebHost,
  "--web-port", "$WebPort"
)

function Quote-ProcessArg {
  param([string]$Value)
  if ($null -eq $Value) {
    return '""'
  }
  if ($Value -notmatch '[\s"]') {
    return $Value
  }
  return '"' + ($Value -replace '"', '\"') + '"'
}

function Join-ProcessArgs {
  param([string[]]$Values)
  return (($Values | ForEach-Object { Quote-ProcessArg $_ }) -join " ")
}

Set-Location $RepoDir
$env:PYTHONUNBUFFERED = "1"

Write-LogLine "Starting BRIC Lightwall web app"
Write-LogLine "RepoDir=$RepoDir"
Write-LogLine "Python=$pythonExe $($pythonPrefixArgs -join ' ')"
Write-LogLine "Command=tools/webapp/app.py --interface $Interface --web-host $WebHost --web-port $WebPort"

try {
  $processArgs = @($pythonPrefixArgs) + @($appArgs)
  $stdoutLog = Join-Path $LogDir "webapp.stdout.log"
  $stderrLog = Join-Path $LogDir "webapp.stderr.log"

  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $pythonExe
  $startInfo.Arguments = Join-ProcessArgs $processArgs
  $startInfo.WorkingDirectory = $RepoDir
  $startInfo.UseShellExecute = $false
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  $startInfo.CreateNoWindow = $true

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $startInfo
  $process.EnableRaisingEvents = $true

  $stdoutWriter = New-Object System.IO.StreamWriter($stdoutLog, $true, [System.Text.Encoding]::UTF8)
  $stderrWriter = New-Object System.IO.StreamWriter($stderrLog, $true, [System.Text.Encoding]::UTF8)

  try {
    $outputHandler = [System.Diagnostics.DataReceivedEventHandler]{
      param($sender, $eventArgs)
      if ($null -ne $eventArgs.Data) {
        $stdoutWriter.WriteLine($eventArgs.Data)
        $stdoutWriter.Flush()
      }
    }
    $errorHandler = [System.Diagnostics.DataReceivedEventHandler]{
      param($sender, $eventArgs)
      if ($null -ne $eventArgs.Data) {
        $stderrWriter.WriteLine($eventArgs.Data)
        $stderrWriter.Flush()
      }
    }
    $process.add_OutputDataReceived($outputHandler)
    $process.add_ErrorDataReceived($errorHandler)

    [void]$process.Start()
    Write-LogLine "Started process id $($process.Id)"
    Write-LogLine "Stdout log: $stdoutLog"
    Write-LogLine "Stderr log: $stderrLog"
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
  } finally {
    $stdoutWriter.Dispose()
    $stderrWriter.Dispose()
    $process.Dispose()
  }

  Write-LogLine "BRIC Lightwall web app exited with code $exitCode"
  exit $exitCode
} catch {
  Write-LogLine "ERROR: $($_.Exception.Message)"
  Write-LogLine "BRIC Lightwall web app exited with code 1"
  exit 1
}
