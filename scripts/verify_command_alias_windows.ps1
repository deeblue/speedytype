[CmdletBinding()]
param(
    [int]$DaemonStartupTimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = "$UserPath;$MachinePath"

function ConvertTo-CmdArgument {
    param([Parameter(Mandatory)][string]$Value)
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Invoke-SpeedyTypeCmd {
    param([Parameter(Mandatory)][string[]]$CommandArguments)

    $line = "speedytype " + (($CommandArguments | ForEach-Object {
        ConvertTo-CmdArgument $_
    }) -join " ")
    $process = Start-Process cmd.exe `
        -ArgumentList @("/d", "/c", $line) `
        -Wait `
        -PassThru `
        -NoNewWindow
    if ($process.ExitCode -ne 0) {
        throw "Command failed ($($process.ExitCode)): $line"
    }
}

Invoke-SpeedyTypeCmd @("diagnose-config")
Invoke-SpeedyTypeCmd @("guided-recording", "--help")

$daemon = Start-Process cmd.exe `
    -ArgumentList @("/d", "/c", "speedytype daemon") `
    -PassThru `
    -WindowStyle Hidden
$stopProbe = $null
try {
    $deadline = (Get-Date).AddSeconds($DaemonStartupTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 250
        $stopProbe = Start-Process cmd.exe `
            -ArgumentList @("/d", "/c", "speedytype daemon-stop") `
            -Wait `
            -PassThru `
            -NoNewWindow
        if ($stopProbe.ExitCode -eq 0) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    if ($null -eq $stopProbe -or $stopProbe.ExitCode -ne 0) {
        throw "Daemon did not become stoppable before timeout."
    }
}
finally {
    Start-Process cmd.exe `
        -ArgumentList @("/d", "/c", "speedytype daemon-stop") `
        -Wait `
        -NoNewWindow | Out-Null
    if (-not $daemon.HasExited) {
        $daemon.WaitForExit(5000) | Out-Null
    }
}

Write-Host "COMMAND_ALIAS_WINDOWS_OK"
