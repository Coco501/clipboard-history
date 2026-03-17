# clipboard-history

A lightweight clipboard history manager for Linux. Runs as a background daemon, captures everything you copy (text and images), and surfaces it in a fast keyboard-driven picker.

![Clipboard History picker](https://raw.githubusercontent.com/yourusername/clipboard-history/main/screenshot.png)

## Features

- **Text & image support** — captures plain text, code snippets, and screenshots
- **Keyboard-driven** — open with `Super+V`, navigate and paste without touching the mouse
- **Fast** — single Tk window, no Electron, no background services eating RAM
- **Live updates** — the picker refreshes automatically as you copy new items
- **Search** — type to instantly filter text entries
- **Works on Wayland and X11**

## Installation

```bash
git clone https://github.com/Coco501/clipboard-history
cd clipboard-history
./scripts/install.sh
```

The installer handles everything:

1. Installs system dependencies (`python3-tk`, `wl-clipboard`, `xclip`)
2. Copies the package to `~/.local/lib/clipboard-history/`
3. Installs the `clipboard-history` command to `~/.local/bin/`
4. Registers a systemd user service that starts automatically with your session
5. Binds `Super+V` as the global shortcut (GNOME only; see below for other DEs)
- Be aware that Ubuntu may have Super+V bound to show notification history by default, this can be unbound in the `Keyboard` section of your settings  

### Optional: image thumbnails

Without extra packages, images appear as `[Image]` placeholders. Install Pillow for actual thumbnails:

```bash
sudo apt install python3-pil python3-pil.imagetk    # Debian/Ubuntu
sudo dnf install python3-pillow                     # Fedora
sudo pacman -S python-pillow                        # Arch
```

## Usage

| Action | Key |
|--------|-----|
| Open picker | `Super+V` |
| Navigate | `↑ / ↓` or `Ctrl+J / Ctrl+K` |
| Paste selected item | `Enter` |
| Delete selected item | `Del` or click `×` |
| Search | Just start typing |
| Close | `Esc` or `Ctrl+W` |

Selecting an item and pressing `Enter` copies it to the clipboard — paste normally with `Ctrl+V` in your target application.

## CLI

```bash
clipboard-history show     # Open the picker (auto-starts daemon)
clipboard-history daemon   # Start the background monitor manually
clipboard-history clear    # Wipe all history
```

## Service management

```bash
systemctl --user status  clipboard-history
systemctl --user restart clipboard-history
systemctl --user stop    clipboard-history
```

## Keyboard shortcut setup

### GNOME
Registered automatically by the installer (`Super+V`).

## Uninstallation

```bash
./scripts/uninstall.sh
```

Stops the service, removes the binary and package, cleans up the GNOME shortcut, and optionally deletes your history data.

## Project structure

```
clipboard_history/
├── config.py      — paths and tuneable constants
├── storage.py     — history persistence (load / save / add / hash)
├── clipboard.py   — clipboard I/O for Wayland and X11
├── daemon.py      — background monitor process
├── ui.py          — Tkinter picker window
└── cli.py         — argument parsing and command dispatch
```

## Requirements

- Python 3.10+
- `python3-tk`
- `wl-clipboard` (Wayland) **or** `xclip` (X11)
- `Pillow` *(optional — image thumbnails)*
