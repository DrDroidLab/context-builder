#!/usr/bin/env bash
# droidctx installer
# Usage: curl -fsSL https://raw.githubusercontent.com/DrDroidLab/context-builder/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/DrDroidLab/context-builder.git"
MIN_PYTHON="3.9"

info()  { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33mWARN:\033[0m %s\n" "$*"; }
error() { printf "\033[1;31mERROR:\033[0m %s\n" "$*" >&2; exit 1; }

# --- Check Python version ---
check_python() {
    local cmd
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            if [ -n "$ver" ]; then
                local major minor
                major=$(echo "$ver" | cut -d. -f1)
                minor=$(echo "$ver" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
                    PYTHON_CMD="$cmd"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# --- Main ---
info "Installing droidctx - Infrastructure context builder for coding agents"
echo ""

if ! check_python; then
    error "Python >= ${MIN_PYTHON} is required but not found. Please install Python first."
fi
info "Found Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"

# Prefer pipx for isolated install
if command -v pipx &>/dev/null; then
    info "Installing with pipx (isolated environment)..."
    pipx install "git+${REPO}" 2>&1
    echo ""
    info "Installed! Run: droidctx --help"

elif command -v pip3 &>/dev/null; then
    info "pipx not found, installing with pip3..."
    warn "Consider installing pipx for better isolation: https://pipx.pypa.io/"
    pip3 install "git+${REPO}" 2>&1
    echo ""
    info "Installed! Run: droidctx --help"

elif command -v pip &>/dev/null; then
    info "Installing with pip..."
    warn "Consider installing pipx for better isolation: https://pipx.pypa.io/"
    pip install "git+${REPO}" 2>&1
    echo ""
    info "Installed! Run: droidctx --help"

else
    error "Neither pipx nor pip found. Please install pip first."
fi

echo ""
info "Quick start:"
echo "  1. droidctx init --path ./my-infra"
echo "  2. Edit ./my-infra/credentials.yaml with your API keys"
echo "  3. droidctx sync --keyfile ./my-infra/credentials.yaml"
echo ""
