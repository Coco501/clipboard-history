#!/usr/bin/env bash
# clipboard-history uninstaller
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
LIB_DIR="$HOME/.local/lib/clipboard-history"
DATA_DIR="$HOME/.local/share/clipboard-history"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="clipboard-history.service"
INSTALL_PATH="$BIN_DIR/clipboard-history"
BINDING_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
section() { echo -e "\n${GREEN}━━━ $* ━━━${NC}"; }

# ── 1. Stop and disable systemd service ───────────────────────────────────────

section "Stopping daemon"

if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
    systemctl --user stop "$SERVICE"
    info "Daemon stopped"
else
    info "Daemon was not running"
fi

if systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null; then
    systemctl --user disable "$SERVICE"
    info "Service disabled"
fi

SERVICE_FILE="$UNIT_DIR/$SERVICE"
if [[ -f "$SERVICE_FILE" ]]; then
    rm -f "$SERVICE_FILE"
    systemctl --user daemon-reload
    info "Service file removed"
fi

# ── 2. Remove the binary ───────────────────────────────────────────────────────

section "Removing binary and package"

if [[ -f "$INSTALL_PATH" ]]; then
    rm -f "$INSTALL_PATH"
    info "Removed $INSTALL_PATH"
else
    info "Binary not found (already removed?)"
fi

if [[ -d "$LIB_DIR" ]]; then
    rm -rf "$LIB_DIR"
    info "Removed $LIB_DIR"
fi

# ── 3. Remove GNOME keybinding ─────────────────────────────────────────────────

section "Removing keyboard shortcut"

if command -v gsettings &>/dev/null && gsettings list-schemas 2>/dev/null | grep -q "org.gnome.settings-daemon"; then
    # Remove the individual binding keys first
    gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        name    2>/dev/null || true
    gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        command 2>/dev/null || true
    gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        binding 2>/dev/null || true

    # Remove our entry from the array, preserving any other custom shortcuts
    NEW_LIST=$(python3 - <<'PYEOF'
import subprocess, ast

result = subprocess.run(
    ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'],
    capture_output=True, text=True
)
raw = result.stdout.strip()

if raw in ('@as []', "['']", '[]', ''):
    existing = []
else:
    if raw.startswith('@as '):
        raw = raw[4:]
    try:
        existing = ast.literal_eval(raw)
    except Exception:
        existing = []

cleaned = [p for p in existing if 'clipboard-history' not in p]

if cleaned:
    print("[" + ", ".join(f"'{p}'" for p in cleaned) + "]")
else:
    print("@as []")
PYEOF
)
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
    info "GNOME Super+V keybinding removed"
else
    warn "GNOME gsettings not available — remove the Super+V shortcut manually from your DE settings"
fi

# ── 4. Prompt to remove history data ──────────────────────────────────────────

section "Clipboard history data"

if [[ -d "$DATA_DIR" ]]; then
    read -r -p "Remove saved clipboard history at $DATA_DIR? [y/N] " REPLY
    if [[ "${REPLY,,}" == "y" ]]; then
        rm -rf "$DATA_DIR"
        info "History data removed"
    else
        info "History data kept at $DATA_DIR"
    fi
else
    info "No history data found"
fi

# ── 5. Done ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}clipboard-history has been uninstalled.${NC}"
echo ""
