#!/usr/bin/env bash
# MMM — Make Modelfiles Matter
# Linux/macOS Installer

set -e

MMM_VERSION="1.0.0"
REPO_URL="https://github.com/yourusername/MMM"

# ── Colors ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[MMM]${NC} $1"; }
success() { echo -e "${GREEN}[MMM]${NC} $1"; }
warn()    { echo -e "${YELLOW}[MMM]${NC} $1"; }
error()   { echo -e "${RED}[MMM]${NC} $1"; exit 1; }

# ── Detect OS ─────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v nixos-version &>/dev/null; then
            echo "nixos"
        else
            echo "linux"
        fi
    else
        error "Unsupported OS: $OSTYPE"
    fi
}

OS=$(detect_os)
info "Detected OS: $OS"

# ── Check dependencies ─────────────────────────────────────────────────────
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        error "Python 3 is required but not found. Please install Python 3.8+ first."
    fi

    PYTHON_VERSION=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [[ $MAJOR -lt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -lt 8 ]]; then
        error "Python 3.8+ required. Found: $PYTHON_VERSION"
    fi

    success "Python $PYTHON_VERSION found"
}

check_ollama() {
    if ! curl -s http://localhost:11434/api/version &>/dev/null; then
        warn "Ollama doesn't appear to be running on localhost:11434"
        warn "Make sure Ollama is installed and running before using MMM"
    else
        success "Ollama is running"
    fi
}

# ── Install ────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/mmm"

install_linux() {
    info "Installing MMM to $INSTALL_DIR..."

    sudo mkdir -p "$INSTALL_DIR/modelfiles"
    sudo cp proxy.py modelfile_to_json.py characters.json "$INSTALL_DIR/"
    sudo chmod 755 "$INSTALL_DIR"
    sudo chmod 644 "$INSTALL_DIR"/*.py "$INSTALL_DIR"/*.json

    info "Installing Python dependencies..."
    $PYTHON -m pip install -r requirements.txt --quiet

    info "Installing systemd service..."
    sudo cp service/ollama-character-proxy.service /etc/systemd/system/mmm.service
    sudo sed -i "s/YOUR_USERNAME/$USER/g" /etc/systemd/system/mmm.service

    # Detect Ollama port
    OLLAMA_PORT=11434
    if ! curl -s http://localhost:11434/api/version &>/dev/null; then
        warn "Ollama not found on 11434 — leaving default config. Edit /etc/systemd/system/mmm.service if needed."
    fi

    sudo systemctl daemon-reload
    sudo systemctl enable mmm
    sudo systemctl start mmm

    success "MMM installed and started as a systemd service"
    info "Proxy is running on port 11435"
    info "Point your Ollama clients at: http://localhost:11435"
    info ""
    info "Useful commands:"
    info "  sudo systemctl status mmm"
    info "  journalctl -u mmm -f"
    info "  sudo systemctl restart mmm"
}

install_macos() {
    INSTALL_DIR="/usr/local/opt/mmm"
    PLIST_DIR="$HOME/Library/LaunchAgents"

    info "Installing MMM to $INSTALL_DIR..."

    sudo mkdir -p "$INSTALL_DIR/modelfiles"
    sudo cp proxy.py modelfile_to_json.py characters.json "$INSTALL_DIR/"

    info "Installing Python dependencies..."
    $PYTHON -m pip install -r requirements.txt --quiet

    mkdir -p "$PLIST_DIR"
    mkdir -p /usr/local/var/log

    PYTHON_PATH=$(which $PYTHON)
    sed "s|/usr/bin/python3|$PYTHON_PATH|g" service/com.mmm.proxy.plist > "$PLIST_DIR/com.mmm.proxy.plist"
    sed -i '' "s|/usr/local/opt/mmm|$INSTALL_DIR|g" "$PLIST_DIR/com.mmm.proxy.plist"

    launchctl load "$PLIST_DIR/com.mmm.proxy.plist"

    success "MMM installed and started via launchd"
    info "Proxy is running on port 11435"
    info "Point your Ollama clients at: http://localhost:11435"
    info ""
    info "Useful commands:"
    info "  launchctl list | grep mmm"
    info "  tail -f /usr/local/var/log/mmm.log"
    info "  launchctl unload ~/Library/LaunchAgents/com.mmm.proxy.plist"
}

install_nixos() {
    warn "NixOS detected."
    warn "For NixOS, use the provided nixos-module.nix instead of this installer."
    warn "See service/nixos-module.nix and the README for instructions."
    exit 0
}

# ── Main ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   MMM — Make Modelfiles Matter       ║${NC}"
echo -e "${BLUE}║   v${MMM_VERSION}                              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

check_python
check_ollama

case $OS in
    linux)  install_linux  ;;
    macos)  install_macos  ;;
    nixos)  install_nixos  ;;
esac

echo ""
success "Installation complete!"
info "Edit $INSTALL_DIR/characters.json to add your characters"
info "Or drop Modelfiles in $INSTALL_DIR/modelfiles/ and run:"
info "  python3 $INSTALL_DIR/modelfile_to_json.py"
echo ""
