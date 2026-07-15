[CmdletBinding()]
param(
    [string]$EnvPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $BootstrapPython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
    & $BootstrapPython -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv."
    }
}

& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install requirements."
}

$Arguments = @("-m", "speedytype")
if ($EnvPath) {
    $Arguments += @("--env", (Resolve-Path -LiteralPath $EnvPath).Path)
}
$Arguments += "install-command"
& $VenvPython @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the speedytype command."
}

Write-Host "Setup complete. Open a new terminal and run: speedytype diagnose-config"
