# MMM — Make Modelfiles Matter
# Windows Installer (PowerShell)
# Run as Administrator: powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [string]$InstallDir = "C:\mmm",
    [int]$ProxyPort = 11435,
    [string]$OllamaHost = "http://localhost:11434"
)

$ErrorActionPreference = "Stop"
$MMM_VERSION = "1.0.0"

function Write-MMM {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[MMM] $Message" -ForegroundColor $Color
}

function Write-Success { Write-MMM $args[0] "Green" }
function Write-Warn    { Write-MMM $args[0] "Yellow" }
function Write-Err     { Write-MMM $args[0] "Red"; exit 1 }

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   MMM — Make Modelfiles Matter       ║" -ForegroundColor Cyan
Write-Host "║   v$MMM_VERSION                              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check admin ────────────────────────────────────────────────────────────
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Err "Please run this script as Administrator (right-click PowerShell → Run as Administrator)"
}

# ── Check Python ───────────────────────────────────────────────────────────
Write-MMM "Checking Python..."
try {
    $pythonVersion = python --version 2>&1
    Write-Success "Found: $pythonVersion"
    $PYTHON = "python"
} catch {
    try {
        $pythonVersion = python3 --version 2>&1
        Write-Success "Found: $pythonVersion"
        $PYTHON = "python3"
    } catch {
        Write-Err "Python 3 not found. Please install Python 3.8+ from https://python.org"
    }
}

# ── Check Ollama ───────────────────────────────────────────────────────────
Write-MMM "Checking Ollama..."
try {
    $response = Invoke-WebRequest -Uri "$OllamaHost/api/version" -UseBasicParsing -TimeoutSec 3
    Write-Success "Ollama is running"
} catch {
    Write-Warn "Ollama not detected at $OllamaHost — make sure it's running before using MMM"
}

# ── Install files ──────────────────────────────────────────────────────────
Write-MMM "Installing MMM to $InstallDir..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\modelfiles" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\logs" | Out-Null

Copy-Item proxy.py, modelfile_to_json.py, characters.json -Destination $InstallDir -Force

# ── Install Python deps ────────────────────────────────────────────────────
Write-MMM "Installing Python dependencies..."
& $PYTHON -m pip install fastapi uvicorn httpx --quiet
if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install Python dependencies" }
Write-Success "Dependencies installed"

# ── Install WinSW service ──────────────────────────────────────────────────
Write-MMM "Installing Windows service..."

$winsw = "$InstallDir\mmm-service.exe"
$winsxmlDest = "$InstallDir\mmm-service.xml"

# Download WinSW
try {
    Write-MMM "Downloading WinSW service wrapper..."
    Invoke-WebRequest -Uri "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" -OutFile $winsw -UseBasicParsing
} catch {
    Write-Warn "Could not download WinSW automatically."
    Write-Warn "Download WinSW manually from https://github.com/winsw/winsw/releases"
    Write-Warn "Save as $winsw and re-run this script, or start manually with:"
    Write-Warn "  cd $InstallDir && $PYTHON proxy.py"
    exit 0
}

# Write service config
$pythonPath = (Get-Command $PYTHON).Source
$xmlContent = @"
<service>
  <id>mmm-proxy</id>
  <name>MMM — Make Modelfiles Matter</name>
  <description>Ollama character injection proxy</description>
  <executable>$pythonPath</executable>
  <arguments>$InstallDir\proxy.py</arguments>
  <workingdirectory>$InstallDir</workingdirectory>
  <env name="OLLAMA_HOST" value="$OllamaHost"/>
  <env name="PROXY_PORT" value="$ProxyPort"/>
  <logpath>$InstallDir\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>5</keepFiles>
  </log>
  <onfailure action="restart" delay="5 sec"/>
</service>
"@
$xmlContent | Out-File -FilePath $winsxmlDest -Encoding UTF8

& $winsw install
& $winsw start

Write-Success "MMM installed and started as a Windows service"
Write-MMM ""
Write-MMM "Proxy running on port $ProxyPort"
Write-MMM "Point your Ollama clients at: http://localhost:$ProxyPort"
Write-MMM ""
Write-MMM "Useful commands:"
Write-MMM "  $winsw status"
Write-MMM "  $winsw restart"
Write-MMM "  $winsw stop"
Write-MMM ""
Write-MMM "Edit $InstallDir\characters.json to add your characters"
Write-Host ""
Write-Success "Installation complete!"
