"""Clipboard history persistence — load, save, add, and hash items."""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, HISTORY_FILE, MAX_ITEMS, SETTINGS_FILE


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def item_hash(item: dict) -> str:
    """Return a stable hash for any item type (text or image)."""
    if item.get("type") == "image":
        try:
            return hashlib.md5(Path(item["path"]).read_bytes()).hexdigest()
        except OSError:
            return md5(item.get("path", ""))
    return md5(item.get("text", ""))


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_history(items: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False))
    os.replace(tmp, HISTORY_FILE)


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False))


def add_item(items: list, text: str) -> list:
    """Deduplicate and prepend a new text item, trimming to MAX_ITEMS."""
    h = md5(text)
    items = [i for i in items if item_hash(i) != h]
    items.insert(0, {
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return items[:MAX_ITEMS]
