$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ScriptDir ".venv"

Write-Host "=== ComputerUse MCP Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check Python
$python = $null
foreach ($p in @("python", "python3")) {
    try {
        $ver = & $p --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) {
                $python = $p
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "ERROR: Python >= 3.10 not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

Write-Host "Python: $python ($(& $python --version))"

# Create venv
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv..."
    & $python -m venv $VenvPath
}

# Install deps
Write-Host "Installing Python dependencies..."
& $venvPython -m pip install -r (Join-Path $ScriptDir "servers\requirements.txt") --disable-pip-version-check -q

# Install Chromium
Write-Host "Installing Chromium browser..."
$playwright = Join-Path $VenvPath "Scripts\playwright.exe"
& $playwright install chromium

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host ""

# Print config
$pythonPath = $venvPython
$mcpPath = Join-Path $ScriptDir "servers\computer_use_mcp.py"

Write-Host "Add this to your agent config:" -ForegroundColor Yellow
Write-Host ""
Write-Host "--- OpenCode (opencode.json) ---" -ForegroundColor White
Write-Host '"mcp": {' 
Write-Host '  "computerUse": {'
Write-Host '    "type": "local",'
Write-Host "    `"command`": [`"$pythonPath`", `"$mcpPath`"],"
Write-Host '    "enabled": true'
Write-Host '  }'
Write-Host '}'
Write-Host ""
Write-Host "--- Claude Code (C:\Users\YOU\.claude.json) ---" -ForegroundColor White
Write-Host '"mcpServers": {'
Write-Host '  "computerUse": {'
Write-Host "    `"command`": `"$pythonPath`","
Write-Host "    `"args`": [`"$mcpPath`"]"
Write-Host '  }'
Write-Host '}'
Write-Host ""
Write-Host "Restart your agent to activate ComputerUse." -ForegroundColor Cyan
