param(
  [string]$RepoDir = "",
  [string]$Interface = "Ethernet",
  [string]$WebHost = "0.0.0.0",
  [int]$WebPort = 8080,
  [string]$Python = "",
  [string]$TaskName = "BRIC Lightwall Web App",
  [string]$WebInterface = "Wi-Fi",
  [switch]$SkipFirewallRules
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an Administrator PowerShell."
  }
}

function Quote-TaskArg {
  param([string]$Value)
  return '"' + ($Value -replace '"', '\"') + '"'
}

function Resolve-StartupPython {
  param(
    [string]$RequestedPython,
    [string]$ResolvedRepoDir
  )

  if ($RequestedPython) {
    return $RequestedPython
  }

  $venvPython = Join-Path $ResolvedRepoDir ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    return $venvPython
  }

  foreach ($candidate in @("python3", "python")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  return ""
}

function Ensure-FirewallRules {
  param(
    [int]$Port,
    [string]$ResolvedPython,
    [string]$DiscoveryInterfaceAlias,
    [string]$WebInterfaceAlias
  )

  foreach ($alias in @($DiscoveryInterfaceAlias, $WebInterfaceAlias)) {
    if (-not $alias) {
      continue
    }
    try {
      Set-NetConnectionProfile -InterfaceAlias $alias -NetworkCategory Private -ErrorAction Stop
    } catch {
      Write-Warning "Could not set interface '$alias' to Private: $($_.Exception.Message)"
    }
  }

  $tcpRuleName = "BRIC Lightwall Web App TCP $Port"
  $existingTcpRule = Get-NetFirewallRule -DisplayName $tcpRuleName -ErrorAction SilentlyContinue
  if ($existingTcpRule) {
    $existingTcpRule | Remove-NetFirewallRule
  }
  New-NetFirewallRule `
    -DisplayName $tcpRuleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Any | Out-Null

  if ($ResolvedPython) {
    $udpRuleName = "BRIC Lightwall Python UDP In"
    $existingUdpRule = Get-NetFirewallRule -DisplayName $udpRuleName -ErrorAction SilentlyContinue
    if ($existingUdpRule) {
      $existingUdpRule | Remove-NetFirewallRule
    }
    New-NetFirewallRule `
      -DisplayName $udpRuleName `
      -Direction Inbound `
      -Program $ResolvedPython `
      -Protocol UDP `
      -Action Allow `
      -Profile Private | Out-Null
  }
}

Assert-Admin

if (-not $RepoDir) {
  $RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
  $RepoDir = (Resolve-Path $RepoDir).Path
}

$launcher = Join-Path $RepoDir "scripts\windows_launch_webapp.ps1"
if (-not (Test-Path $launcher)) {
  throw "Launcher script not found: $launcher"
}

$logDir = Join-Path $RepoDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$Python = Resolve-StartupPython -RequestedPython $Python -ResolvedRepoDir $RepoDir

if (-not $SkipFirewallRules) {
  Ensure-FirewallRules `
    -Port $WebPort `
    -ResolvedPython $Python `
    -DiscoveryInterfaceAlias $Interface `
    -WebInterfaceAlias $WebInterface
}

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$taskArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", (Quote-TaskArg $launcher),
  "-RepoDir", (Quote-TaskArg $RepoDir),
  "-Interface", (Quote-TaskArg $Interface),
  "-WebHost", (Quote-TaskArg $WebHost),
  "-WebPort", "$WebPort",
  "-LogDir", (Quote-TaskArg $logDir)
)

if ($Python) {
  $taskArgs += @("-Python", (Quote-TaskArg $Python))
} else {
  Write-Warning "No Python executable was resolved at install time. The launcher will try to resolve Python at startup."
}

$action = New-ScheduledTaskAction `
  -Execute $powershellExe `
  -Argument ($taskArgs -join " ") `
  -WorkingDirectory $RepoDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
  -UserId "SYSTEM" `
  -LogonType ServiceAccount `
  -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
  -MultipleInstances IgnoreNew `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Description "Starts the BRIC Lightwall web app at Windows startup." `
  -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$task = Get-ScheduledTask -TaskName $TaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host "Installed scheduled task: $TaskName"
Write-Host "State: $($task.State)"
Write-Host "LastTaskResult: $($taskInfo.LastTaskResult)"
Write-Host "Log: $(Join-Path $logDir 'webapp.log')"
Write-Host "URL: http://localhost:$WebPort"
if ($WebHost -eq "0.0.0.0") {
  $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notlike "127.*" -and
      $_.IPAddress -notlike "169.254.*" -and
      $_.PrefixOrigin -ne "WellKnown"
    }
  foreach ($address in $addresses) {
    Write-Host "LAN URL: http://$($address.IPAddress):$WebPort"
  }
}
