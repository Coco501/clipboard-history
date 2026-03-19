#!/usr/bin/env bash
# clipboard-history installer
# Supports: Ubuntu/Debian (apt), Fedora/RHEL (dnf), Arch (pacman)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
LIB_DIR="$HOME/.local/lib/clipboard-history"
DATA_DIR="$HOME/.local/share/clipboard-history"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="clipboard-history.service"
INSTALL_PATH="$BIN_DIR/clipboard-history"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; }
section() { echo -e "\n${GREEN}━━━ $* ━━━${NC}"; }

# ── 1. Detect package manager & install system deps ───────────────────────────

section "Installing dependencies"

install_apt() {
    # Update package lists; ignore errors from third-party repos (e.g. VS Code,
    # Chrome) that may have stale Release files — they don't affect our packages.
    sudo apt-get update -qq 2>&1 | grep -v "^E:" || true
    sudo apt-get install -y python3 python3-tk wl-clipboard xclip xdotool
}

install_dnf() {
    sudo dnf install -y python3 python3-tkinter wl-clipboard xclip xdotool
}

install_pacman() {
    sudo pacman -Sy --noconfirm python tk wl-clipboard xclip xdotool
}

if command -v apt-get &>/dev/null; then
    info "Detected apt (Debian/Ubuntu)"
    install_apt
elif command -v dnf &>/dev/null; then
    info "Detected dnf (Fedora/RHEL)"
    install_dnf
elif command -v pacman &>/dev/null; then
    info "Detected pacman (Arch)"
    install_pacman
else
    warn "Unknown package manager. Please manually install: python3, python3-tk, wl-clipboard or xclip"
fi

# Verify python3 and tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    error "python3-tk (tkinter) is not available. Install it and re-run this script."
    exit 1
fi
info "python3 + tkinter OK"

# ── 2. Install the script ─────────────────────────────────────────────────────

section "Installing clipboard-history"

mkdir -p "$BIN_DIR" "$DATA_DIR" "$LIB_DIR"

# Copy the Python package
cp -r "$SCRIPT_DIR/clipboard_history" "$LIB_DIR/"

# Write the entry-point script that puts the package on sys.path
cat > "$INSTALL_PATH" << PYEOF
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.expanduser('~/.local/lib/clipboard-history'))
from clipboard_history import main
main()
PYEOF
chmod +x "$INSTALL_PATH"
info "Installed to $INSTALL_PATH (package at $LIB_DIR)"

# Ensure ~/.local/bin is on PATH (add to shell rc if missing)
for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [[ -f "$RC" ]] && ! grep -q 'local/bin' "$RC"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
        info "Added ~/.local/bin to PATH in $RC"
    fi
done

if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 3. Install systemd user service ───────────────────────────────────────────

section "Setting up systemd user service"

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$SERVICE" << EOF
[Unit]
Description=Clipboard History Daemon
Documentation=https://github.com/yourusername/clipboard-history
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=${INSTALL_PATH} daemon
Restart=on-failure
RestartSec=3s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE"
systemctl --user start "$SERVICE"
info "Systemd user service enabled and started"

if systemctl --user is-active --quiet "$SERVICE"; then
    info "Daemon is running ✓"
else
    warn "Daemon failed to start. Check: systemctl --user status clipboard-history"
fi

# ── 4. Register Super+V keyboard shortcut ─────────────────────────────────────

# Check if Super+V is already bound to something before we register it.
check_superv_conflict() {
    local conflict=""

    # ── GNOME ──────────────────────────────────────────────────────────────────
    if command -v gsettings &>/dev/null && \
       gsettings list-schemas 2>/dev/null | grep -q "org.gnome.settings-daemon"; then

        # Custom keybindings
        local paths_raw
        paths_raw=$(gsettings get org.gnome.settings-daemon.plugins.media-keys \
                        custom-keybindings 2>/dev/null || echo "")
        while IFS= read -r path; do
            local binding
            binding=$(gsettings get \
                "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${path}" \
                binding 2>/dev/null || echo "")
            if echo "$binding" | grep -qi "<Super>v"; then
                local name
                name=$(gsettings get \
                    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${path}" \
                    name 2>/dev/null | tr -d "'")
                conflict="GNOME custom shortcut: '${name}'"
            fi
        done < <(echo "$paths_raw" | grep -oP "'/[^']+'" | tr -d "'" || true)

        # Built-in GNOME schemas (list-recursively takes one schema at a time)
        if [[ -z "$conflict" ]]; then
            local match
            match=$(  { gsettings list-recursively org.gnome.shell.keybindings 2>/dev/null || true; \
                        gsettings list-recursively org.gnome.desktop.wm.keybindings 2>/dev/null || true; } \
                    | grep -i "<Super>v" | head -1 || true)
            [[ -n "$match" ]] && conflict="a built-in GNOME keybinding"
        fi
    fi

    # ── i3 ─────────────────────────────────────────────────────────────────────
    if [[ -z "$conflict" ]]; then
        for cfg in "$HOME/.config/i3/config" "$HOME/.i3/config"; do
            [[ -f "$cfg" ]] || continue
            # Resolve what $mod is set to in the config
            local mod_val
            mod_val=$(grep -iP '^\s*set\s+\$mod\s+' "$cfg" | \
                      awk '{print $NF}' | head -1)
            # Warn if $mod+v is bound and $mod resolves to Mod4/Super
            if echo "$mod_val" | grep -qi "Mod4\|Super"; then
                { grep -qiP '^\s*bindsym\s+\$mod\+v\b' "$cfg" && \
                    conflict="i3 config (${cfg}): bindsym \$mod+v"; } || true
            fi
            # Also catch explicit Mod4+v / Super+v regardless of $mod
            { grep -qiP '^\s*bindsym\s+(Mod4|Super)\+v\b' "$cfg" && \
                conflict="i3 config (${cfg}): bindsym Mod4+v"; } || true
        done
    fi

    # ── Sway ───────────────────────────────────────────────────────────────────
    if [[ -z "$conflict" ]]; then
        for cfg in "$HOME/.config/sway/config" "$HOME/.sway/config"; do
            [[ -f "$cfg" ]] || continue
            local mod_val
            mod_val=$(grep -iP '^\s*set\s+\$mod\s+' "$cfg" | \
                      awk '{print $NF}' | head -1 || true)
            if echo "$mod_val" | grep -qi "Mod4\|Super"; then
                { grep -qiP '^\s*bindsym\s+\$mod\+v\b' "$cfg" && \
                    conflict="Sway config (${cfg}): bindsym \$mod+v"; } || true
            fi
            { grep -qiP '^\s*bindsym\s+(Mod4|Super)\+v\b' "$cfg" && \
                conflict="Sway config (${cfg}): bindsym Mod4+v"; } || true
        done
    fi

    # ── KDE ────────────────────────────────────────────────────────────────────
    if [[ -z "$conflict" ]]; then
        local kde_cfg="$HOME/.config/kglobalshortcutsrc"
        if [[ -f "$kde_cfg" ]] && grep -qiP "Meta\+V" "$kde_cfg"; then
            local kde_action
            kde_action=$(grep -iP "Meta\+V" "$kde_cfg" | head -1 | cut -d= -f1)
            conflict="KDE global shortcut: '${kde_action}'"
        fi
    fi

    if [[ -n "$conflict" ]]; then
        echo ""
        echo -e "${YELLOW}┌─────────────────────────────────────────────────────────┐${NC}"
        echo -e "${YELLOW}│  ⚠  Super+V conflict detected                           │${NC}"
        echo -e "${YELLOW}│                                                         │${NC}"
        printf  "${YELLOW}│  Already bound in: %-38s│${NC}\n" "$conflict"
        echo -e "${YELLOW}│                                                         │${NC}"
        echo -e "${YELLOW}│  The shortcut will be overwritten below. Change it in   │${NC}"
        echo -e "${YELLOW}│  your DE settings if you want to keep both.             │${NC}"
        echo -e "${YELLOW}└─────────────────────────────────────────────────────────┘${NC}"
        echo ""
    fi
}

check_superv_conflict

section "Registering Super+V keyboard shortcut"

BINDING_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"

if command -v gsettings &>/dev/null && gsettings list-schemas 2>/dev/null | grep -q "org.gnome.settings-daemon"; then
    info "Detected GNOME — registering gsettings custom keybinding"

    # Read existing custom keybindings, remove any stale clipboard-history entry, add new one
    EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "@as []")

    # Use Python to safely merge the binding path into the existing array
    NEW_LIST=$(python3 - <<'PYEOF'
import subprocess, ast, sys

result = subprocess.run(
    ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'],
    capture_output=True, text=True
)
raw = result.stdout.strip()

# Parse GVariant array-of-strings into a Python list
if raw in ('@as []', "['']", '[]', ''):
    existing = []
else:
    # Strip GVariant prefix if present
    if raw.startswith('@as '):
        raw = raw[4:]
    try:
        existing = ast.literal_eval(raw)
    except Exception:
        existing = []

new_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/'
cleaned = [p for p in existing if 'clipboard-history' not in p]
cleaned.append(new_path)
# Format as GVariant string list
print("[" + ", ".join(f"'{p}'" for p in cleaned) + "]")
PYEOF
)

    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"

    gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        name 'Clipboard History'
    gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        command "${INSTALL_PATH} show"
    gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BINDING_PATH}" \
        binding '<Super>v'

    info "Super+V shortcut registered for GNOME ✓"

elif command -v kwriteconfig5 &>/dev/null || command -v kwriteconfig6 &>/dev/null; then
    warn "KDE detected. Add the shortcut manually:"
    echo "  System Settings → Shortcuts → Custom Shortcuts → Edit → New → Command/URL"
    echo "  Name: Clipboard History"
    echo "  Command: ${INSTALL_PATH} show"
    echo "  Shortcut: Meta+V"

elif [[ "${XDG_SESSION_TYPE:-}" == "x11" ]] && command -v xbindkeys &>/dev/null; then
    warn "X11 session detected with xbindkeys. Add to ~/.xbindkeysrc:"
    echo "  \"${INSTALL_PATH} show\""
    echo "  Mod4 + v"

else
    warn "Could not auto-register Super+V. Add manually via your DE's shortcut settings:"
    echo "  Command: ${INSTALL_PATH} show"
    echo "  Shortcut: Super+V"
fi

# ── 5. Done ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     clipboard-history installed!             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Press Super+V to open clipboard history"
echo ""
echo "  Commands:"
echo "    clipboard-history show     Open the picker"
echo "    clipboard-history clear    Wipe history"
echo "    clipboard-history daemon   Run daemon manually"
echo ""
echo "  Service management:"
echo "    systemctl --user status clipboard-history"
echo "    systemctl --user restart clipboard-history"
echo "    systemctl --user stop clipboard-history"
echo ""
