#!/usr/bin/env bash
# droidctx installer v2
# Usage: curl -fsSL https://raw.githubusercontent.com/DrDroidLab/context-builder/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/DrDroidLab/context-builder.git"
MIN_PYTHON="3.9"
INSTALL_DIR="$HOME/.droidctx"

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
                if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
                    PYTHON_CMD="$cmd"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# --- Add to PATH helper ---
add_to_path() {
    local bin_dir="$1"
    local shell_rc=""

    if [ -f "$HOME/.zshrc" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        shell_rc="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        shell_rc="$HOME/.bash_profile"
    fi

    if [ -n "$shell_rc" ]; then
        if ! grep -q "$bin_dir" "$shell_rc" 2>/dev/null; then
            echo "" >> "$shell_rc"
            echo "# droidctx" >> "$shell_rc"
            echo "export PATH=\"$bin_dir:\$PATH\"" >> "$shell_rc"
            info "Added $bin_dir to PATH in $shell_rc"
            warn "Run 'source $shell_rc' or open a new terminal to use droidctx"
        fi
    else
        warn "Could not find shell rc file. Add this to your shell profile:"
        echo "  export PATH=\"$bin_dir:\$PATH\""
    fi
}

# --- Detect OS/platform ---
detect_platform() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    case "$OS" in
        Darwin) PLATFORM="macos" ;;
        Linux)  PLATFORM="linux" ;;
        *)      PLATFORM="unknown" ;;
    esac
}

# --- Install Python if missing ---
install_python() {
    detect_platform

    echo ""
    warn "Python >= ${MIN_PYTHON} is required but not found."
    echo ""

    # When piped via curl, stdin is the pipe — reopen from terminal for prompt
    if [ ! -t 0 ]; then
        exec < /dev/tty
    fi

    printf "  Would you like to install Python automatically? [Y/n] "
    read -r answer
    answer="${answer:-Y}"

    case "$answer" in
        [Yy]|[Yy][Ee][Ss]) ;;
        *) error "Python is required. Install it manually and re-run the installer." ;;
    esac

    if [ "$PLATFORM" = "macos" ]; then
        if command -v brew &>/dev/null; then
            info "Installing Python via Homebrew..."
            brew install python@3.12
        else
            info "Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Source brew shellenv for current session
            if [ -x "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -x "/usr/local/bin/brew" ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            info "Installing Python via Homebrew..."
            brew install python@3.12
        fi

    elif [ "$PLATFORM" = "linux" ]; then
        if command -v apt-get &>/dev/null; then
            info "Installing Python via apt..."
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-venv python3-pip
        elif command -v dnf &>/dev/null; then
            info "Installing Python via dnf..."
            sudo dnf install -y python3 python3-pip
        elif command -v yum &>/dev/null; then
            info "Installing Python via yum..."
            sudo yum install -y python3 python3-pip
        elif command -v apk &>/dev/null; then
            info "Installing Python via apk..."
            sudo apk add python3 py3-pip
        elif command -v pacman &>/dev/null; then
            info "Installing Python via pacman..."
            sudo pacman -Sy --noconfirm python python-pip
        else
            error "Could not detect package manager. Install Python >= ${MIN_PYTHON} manually and re-run."
        fi
    else
        error "Unsupported OS: $OS. Install Python >= ${MIN_PYTHON} manually and re-run."
    fi

    # Refresh PATH and re-check
    hash -r 2>/dev/null || true
    if ! check_python; then
        error "Python installation succeeded but version check failed. Please open a new terminal and re-run."
    fi
    info "Python installed: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"
}

# --- Main ---
info "Installing droidctx - Infrastructure context builder for coding agents"
echo ""

if ! check_python; then
    install_python
fi
info "Found Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"

# Strategy 1: pipx (best isolation)
if command -v pipx &>/dev/null; then
    info "Installing with pipx (isolated environment)..."
    pipx install "git+${REPO}" 2>&1
    echo ""
    info "Installed! Run: droidctx --help"

# Strategy 2: Create a dedicated venv (works on externally-managed Python)
else
    info "Creating isolated environment at $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    "$PYTHON_CMD" -m venv "$INSTALL_DIR"

    info "Installing droidctx into $INSTALL_DIR..."
    "$INSTALL_DIR/bin/pip" install --upgrade pip -q 2>&1
    "$INSTALL_DIR/bin/pip" install "git+${REPO}" 2>&1

    # Symlink binary to ~/.local/bin
    LOCAL_BIN="$HOME/.local/bin"
    mkdir -p "$LOCAL_BIN"
    ln -sf "$INSTALL_DIR/bin/droidctx" "$LOCAL_BIN/droidctx"

    # Ensure ~/.local/bin is in PATH
    if ! echo "$PATH" | tr ':' '\n' | grep -q "^$LOCAL_BIN$"; then
        add_to_path "$LOCAL_BIN"
    fi

    echo ""
    info "Installed! Binary at: $LOCAL_BIN/droidctx"

    # Test if it's reachable
    if command -v droidctx &>/dev/null; then
        info "droidctx is ready. Run: droidctx --help"
    else
        info "Run: $LOCAL_BIN/droidctx --help"
        warn "Or open a new terminal for PATH to take effect"
    fi
fi

echo ""
info "Quick start:"
echo "  1. droidctx init"
echo "  2. droidctx detect                (auto-detect kubectl, aws, gcloud, az)"
echo "  3. Edit ./droidctx-context/credentials.yaml with your API keys"
echo "  4. droidctx sync"
echo ""
