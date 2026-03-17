from pathlib import Path

DATA_DIR      = Path.home() / ".local/share/clipboard-history"
HISTORY_FILE  = DATA_DIR / "history.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
PID_FILE      = DATA_DIR / "daemon.pid"

MAX_ITEMS     = 50
POLL_INTERVAL = 1.0   # seconds between clipboard polls
IMAGE_RECHECK = 2.0   # seconds between image re-reads while clipboard is non-text
