"""Background daemon — monitors the clipboard and persists history."""

import atexit
import hashlib
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from .clipboard import detect_session, read_clipboard_image
from .config import DATA_DIR, IMAGE_RECHECK, MAX_ITEMS, PID_FILE, POLL_INTERVAL
from .storage import add_item, load_history, md5, save_history


def is_daemon_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
        return "clipboard" in cmdline
    except (OSError, ValueError):
        return False


def cmd_daemon() -> None:
    """Run the background clipboard monitor.

    Uses a hidden Tk window for clipboard access instead of spawning
    wl-paste/xclip every second, which eliminates focus-flicker.
    Images are re-checked every IMAGE_RECHECK seconds while the clipboard
    is non-text, catching back-to-back screenshots without constant polling.
    """
    import tkinter as tk

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    session = detect_session()

    def cleanup(*_):
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    atexit.register(lambda: PID_FILE.exists() and PID_FILE.unlink())

    root = tk.Tk()
    root.withdraw()  # invisible — only used for clipboard access

    last_hash           = [None]
    last_image_check_at = [0.0]

    # Seed so we don't re-record whatever is already in the clipboard
    try:
        content = root.clipboard_get()
        if content:
            last_hash[0] = md5(content)
    except tk.TclError:
        pass

    def check_clipboard():
        try:
            content = root.clipboard_get()
            last_image_check_at[0] = 0.0  # reset so next image is caught promptly
            if content:
                h = md5(content)
                if h != last_hash[0]:
                    last_hash[0] = h
                    hist = load_history()
                    hist = add_item(hist, content)
                    save_history(hist)
        except tk.TclError:
            # Clipboard is non-text. Re-check for a new image every IMAGE_RECHECK
            # seconds — frequent enough for back-to-back screenshots, infrequent
            # enough to avoid the focus-flicker caused by constant subprocess calls.
            now = time.monotonic()
            if now - last_image_check_at[0] >= IMAGE_RECHECK:
                last_image_check_at[0] = now
                img_bytes = read_clipboard_image(session)
                if img_bytes:
                    h = hashlib.md5(img_bytes).hexdigest()
                    if h != last_hash[0]:
                        last_hash[0] = h
                        img_path = DATA_DIR / f"img_{h[:16]}.png"
                        try:
                            img_path.write_bytes(img_bytes)
                            hist = load_history()
                            hist.insert(0, {
                                "type": "image",
                                "path": str(img_path),
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            })
                            save_history(hist[:MAX_ITEMS])
                        except OSError:
                            pass

        root.after(int(POLL_INTERVAL * 1000), check_clipboard)

    print(f"[clipboard-history] daemon started (PID {os.getpid()})", flush=True)
    check_clipboard()
    root.mainloop()
