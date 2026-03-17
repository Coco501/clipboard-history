"""Clipboard I/O abstraction for Wayland and X11."""

import os
import subprocess
from pathlib import Path


def detect_session() -> str:
    """Return 'wayland' or 'x11'."""
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    return "x11"


def read_clipboard(session: str) -> str | None:
    """Read current clipboard text. Returns None on failure or empty clipboard."""
    if session == "wayland":
        cmds = [["wl-paste", "--no-newline"], ["wl-paste"]]
    else:
        cmds = [
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode != 0:
                continue
            text = result.stdout.decode("utf-8", errors="replace").rstrip("\n")
            return text if text else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def set_clipboard(text: str, session: str) -> bool:
    """Write text to the clipboard."""
    if session == "wayland":
        try:
            subprocess.run(["wl-copy"], input=text.encode(), timeout=2)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return False

    # X11: xclip must stay alive as the selection owner until another app reads it.
    for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.stdin.write(text.encode())
            p.stdin.close()
            return True
        except FileNotFoundError:
            continue
    return False


def read_clipboard_image(session: str) -> bytes | None:
    """Try to read image/png from the clipboard. Returns raw bytes or None."""
    if session == "wayland":
        try:
            r = subprocess.run(["wl-paste", "--type", "image/png"],
                               capture_output=True, timeout=2)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            r = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                capture_output=True, timeout=2)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def set_clipboard_image(path: str, session: str) -> bool:
    """Write an image file to the clipboard."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False

    if session == "wayland":
        try:
            subprocess.run(["wl-copy", "--type", "image/png"], input=data, timeout=2)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard", "-t", "image/png"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            p.stdin.write(data)
            p.stdin.close()
            return True
        except FileNotFoundError:
            pass
    return False
