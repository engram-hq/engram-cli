#!/usr/bin/env bash
# Engram CLI - one-line installer / upgrader
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/engram-hq/engram-cli/main/install.sh | bash
#
# What it does:
#   1. Installs pipx if not present (via brew on macOS, pip on Linux)
#   2. Installs or upgrades engram-cli via pipx
#   3. Installs Ollama if not present (via brew on macOS, official script on Linux)
#   4. Verifies everything works

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

info()  { echo -e "${CYAN}${BOLD}==> ${RESET}${BOLD}$*${RESET}"; }
ok()    { echo -e "${GREEN}${BOLD}  ✓ ${RESET}$*"; }
warn()  { echo -e "${YELLOW}${BOLD}  ! ${RESET}$*"; }

echo ""
echo -e "${CYAN}${BOLD}Engram CLI Installer${RESET}"
echo ""

# --- 1. Ensure pipx ---
if command -v pipx &>/dev/null; then
    ok "pipx found"
else
    info "Installing pipx..."
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install pipx
            pipx ensurepath
        else
            warn "Homebrew not found. Install brew first: https://brew.sh"
            exit 1
        fi
    else
        python3 -m pip install --user pipx 2>/dev/null || pip install --user pipx
        python3 -m pipx ensurepath 2>/dev/null || pipx ensurepath
    fi
    ok "pipx installed"
fi

# --- 2. Install or upgrade engram-cli ---
if command -v engram &>/dev/null; then
    CURRENT=$(engram version 2>/dev/null | head -1 | grep -o 'v[0-9.]*' || echo "unknown")
    info "Upgrading engram-cli (current: ${CURRENT})..."
    if pipx upgrade engram-cli 2>/dev/null; then
        ok "Upgraded"
    else
        # Upgrade fails if installed from local path — force reinstall from PyPI
        pipx install engram-cli --force
        ok "Reinstalled from PyPI"
    fi
else
    info "Installing engram-cli..."
    pipx install engram-cli
    ok "Installed"
fi

NEW_VERSION=$(engram version 2>/dev/null | head -1 || echo "engram-cli installed")
ok "${NEW_VERSION}"

# --- 3. Ensure Ollama ---
if command -v ollama &>/dev/null; then
    ok "Ollama found"
else
    info "Installing Ollama..."
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install ollama
        else
            warn "Install Ollama manually: https://ollama.com/download"
        fi
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    ok "Ollama installed"
fi

# --- 4. Summary ---
echo ""
echo -e "${GREEN}${BOLD}Ready!${RESET} Run:"
echo ""
echo "  engram analyze .                    # analyze current repo"
echo "  engram analyze owner/repo           # analyze any GitHub repo"
echo "  engram upgrade                      # upgrade to latest version"
echo "  engram browse                       # visual dashboard"
echo ""
