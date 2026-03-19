"""Tkinter picker UI — shown when the user opens clipboard history."""

import ctypes
import ctypes.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from .clipboard import detect_session, set_clipboard, set_clipboard_image
from .daemon import is_daemon_running
from .storage import item_hash, load_history, load_settings, save_history, save_settings

# ── Colour palettes ────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        # Catppuccin Mocha-inspired
        "bg":        "#1e1e2e",
        "surface":   "#2a2a3c",
        "surface1":  "#313244",
        "overlay":   "#585b70",
        "text":      "#cdd6f4",
        "subtext":   "#a6adc8",
        "accent":    "#89b4fa",
        "select_bg": "#2d4f7c",
        "red":       "#f38ba8",
    },
    "light": {
        # Dawnfox-inspired: warm cream background, muted purple text, pine accent
        "bg":        "#faf4ed",
        "surface":   "#f2e9de",
        "surface1":  "#e4dfde",
        "overlay":   "#9893a5",
        "text":      "#575279",
        "subtext":   "#797593",
        "accent":    "#286983",
        "select_bg": "#dfdad9",
        "red":       "#b4637a",
    },
}

THEME_ICON = {"dark": "☾", "light": "☀"}


# ── Monitor geometry ───────────────────────────────────────────────────────────

def _get_current_monitor(root):
    """Return (x, y, w, h) of the monitor containing the mouse cursor."""
    fallback = (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    try:
        cx, cy = root.winfo_pointerx(), root.winfo_pointery()
    except Exception:
        return fallback

    def _parse_monitors(cmd):
        """Run cmd and extract [(mx, my, mw, mh), ...] from WxH+X+Y tokens."""
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return []
        monitors = []
        for m in re.finditer(r'(\d+)x(\d+)\+(\d+)\+(\d+)', out):
            mw, mh, mx, my = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if mw > 0 and mh > 0:
                monitors.append((mx, my, mw, mh))
        return monitors

    # Try xrandr (X11 / XWayland), then wlr-randr (wlroots Wayland compositors).
    monitors = _parse_monitors(["xrandr", "--query"]) or \
               _parse_monitors(["wlr-randr"])

    for mx, my, mw, mh in monitors:
        if mx <= cx < mx + mw and my <= cy < my + mh:
            return (mx, my, mw, mh)
    return fallback


# ── Picker window ──────────────────────────────────────────────────────────────

def cmd_show() -> None:
    # Auto-start daemon if not running
    if not is_daemon_running():
        subprocess.Popen(
            [sys.executable, sys.argv[0], "daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(0.4)

    try:
        import tkinter as tk
    except ImportError:
        print("Error: python3-tk is not installed.\n"
              "Run: sudo apt install python3-tk", file=sys.stderr)
        sys.exit(1)

    items = load_history()
    session = detect_session()

    # ── Theme state ───────────────────────────────────────────────────────────

    settings     = load_settings()
    active_theme = [settings.get("theme", "dark")]
    C            = dict(THEMES[active_theme[0]])

    # ── Window ────────────────────────────────────────────────────────────────

    root = tk.Tk()
    root.title("Clipboard History")
    root.resizable(True, True)

    W, H = 560, 540
    mx, my, mw, mh = _get_current_monitor(root)
    root.geometry(f"{W}x{H}+{mx + (mw - W) // 2}+{my + max(0, (mh - H) // 2 - 40)}")
    root.minsize(380, 300)
    root.configure(bg=C["bg"])

    outer = tk.Frame(root, bg=C["bg"])
    outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(12, 8))

    # ── Header ────────────────────────────────────────────────────────────────

    header = tk.Frame(outer, bg=C["bg"])
    header.pack(fill=tk.X, pady=(0, 10))

    title_lbl = tk.Label(header, text="⎘  Clipboard History",
                         fg=C["accent"], bg=C["bg"],
                         font=("Sans Serif", 12, "bold"))
    title_lbl.pack(side=tk.LEFT)

    theme_btn = tk.Label(header, text=THEME_ICON[active_theme[0]],
                         fg=C["subtext"], bg=C["bg"],
                         font=("Sans Serif", 13), cursor="hand2", padx=6)
    theme_btn.pack(side=tk.RIGHT)

    clear_btn = tk.Label(header, text="🧹",
                         fg=C["subtext"], bg=C["bg"],
                         font=("Sans Serif", 13), cursor="hand2", padx=6)
    clear_btn.pack(side=tk.RIGHT)

    count_var = tk.StringVar(value=f"{len(items)} items")
    count_lbl = tk.Label(header, textvariable=count_var,
                         fg=C["subtext"], bg=C["bg"],
                         font=("Sans Serif", 9))
    count_lbl.pack(side=tk.RIGHT)

    # ── Search box (Canvas-backed rounded rectangle) ──────────────────────────

    search_var = tk.StringVar()
    SEARCH_H, RADIUS = 44, 10

    search_canvas = tk.Canvas(outer, height=SEARCH_H, bg=C["bg"],
                               highlightthickness=0, bd=0)
    search_canvas.pack(fill=tk.X, pady=(0, 10))

    def _draw_search_bg(border_color):
        search_canvas.delete("bg")
        w = search_canvas.winfo_width()
        if w <= 1:
            return
        r, h = RADIUS, SEARCH_H
        pts = [r, 0,  w-r, 0,  w, 0,  w, r,
               w, h-r,  w, h,  w-r, h,  r, h,
               0, h,  0, h-r,  0, r,  0, 0]
        search_canvas.create_polygon(pts, smooth=True,
                                      fill=C["surface"], outline=border_color,
                                      width=1.5, tags="bg")

    search_entry = tk.Entry(search_canvas, textvariable=search_var,
                             bg=C["surface"], fg=C["text"],
                             insertbackground=C["accent"],
                             relief=tk.FLAT, bd=0, highlightthickness=0,
                             font=("Monospace", 10))
    _entry_win = search_canvas.create_window(16, SEARCH_H // 2, anchor="w",
                                              window=search_entry,
                                              height=SEARCH_H - 16)

    def _on_search_configure(e):
        _draw_search_bg(C["overlay"])
        search_canvas.itemconfig(_entry_win, width=e.width - 32)

    search_canvas.bind("<Configure>", _on_search_configure)
    search_entry.bind("<FocusIn>",  lambda e: _draw_search_bg(C["accent"]))
    search_entry.bind("<FocusOut>", lambda e: _draw_search_bg(C["overlay"]))

    # ── Scrollable item list ───────────────────────────────────────────────────

    list_outer = tk.Frame(outer, bg=C["bg"])
    list_outer.pack(fill=tk.BOTH, expand=True)

    list_scrollbar = tk.Scrollbar(list_outer, bg=C["surface1"], troughcolor=C["bg"],
                                   relief=tk.FLAT, bd=0, width=6,
                                   activebackground=C["overlay"])
    list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    list_canvas = tk.Canvas(list_outer, bg=C["bg"], highlightthickness=0, bd=0,
                             yscrollcommand=list_scrollbar.set)
    list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    list_scrollbar.config(command=list_canvas.yview)

    items_frame = tk.Frame(list_canvas, bg=C["bg"])
    items_win   = list_canvas.create_window((0, 0), window=items_frame, anchor="nw")

    items_frame.bind("<Configure>",
                     lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
    list_canvas.bind("<Configure>",
                     lambda e: list_canvas.itemconfig(items_win, width=e.width))
    list_canvas.bind("<Button-4>", lambda e: list_canvas.yview_scroll(-1, "units"))
    list_canvas.bind("<Button-5>", lambda e: list_canvas.yview_scroll(+1, "units"))

    # ── Footer ────────────────────────────────────────────────────────────────

    footer = tk.Frame(outer, bg=C["bg"], pady=5)
    footer.pack(fill=tk.X)
    footer_lbl = tk.Label(footer,
                           text="↑/↓  Ctrl+J/K  navigate    Enter  paste    Del/×  remove    Esc/Ctrl+W  close",
                           fg=C["overlay"], bg=C["bg"], font=("Sans Serif", 8))
    footer_lbl.pack()

    # ── State ─────────────────────────────────────────────────────────────────

    filtered_items = []
    current_rows   = []   # list of (row_frame, primary_widget, xbtn)
    selected_idx   = [0]
    _photo_refs    = []   # prevents Tk from GC-ing PhotoImage objects

    # ── Theme application ─────────────────────────────────────────────────────

    def _apply_theme():
        """Reconfigure every static widget and rebuild the list with new colours."""
        root.configure(bg=C["bg"])
        for w in (outer, header, list_outer, items_frame, footer):
            w.configure(bg=C["bg"])
        title_lbl.configure(fg=C["accent"], bg=C["bg"])
        count_lbl.configure(fg=C["subtext"], bg=C["bg"])
        theme_btn.configure(fg=C["subtext"], bg=C["bg"],
                            text=THEME_ICON[active_theme[0]])
        search_canvas.configure(bg=C["bg"])
        search_entry.configure(bg=C["surface"], fg=C["text"],
                                insertbackground=C["accent"])
        list_canvas.configure(bg=C["bg"])
        list_scrollbar.configure(bg=C["surface1"], troughcolor=C["bg"],
                                  activebackground=C["overlay"])
        footer_lbl.configure(fg=C["overlay"], bg=C["bg"])
        _draw_search_bg(C["overlay"])
        _filter()

    def _toggle_theme(event=None):
        active_theme[0] = "light" if active_theme[0] == "dark" else "dark"
        C.update(THEMES[active_theme[0]])
        save_settings({"theme": active_theme[0]})
        _apply_theme()

    theme_btn.bind("<Button-1>", _toggle_theme)
    theme_btn.bind("<Enter>", lambda e: theme_btn.configure(fg=C["accent"]))
    theme_btn.bind("<Leave>", lambda e: theme_btn.configure(fg=C["subtext"]))

    # ── Row helpers ───────────────────────────────────────────────────────────

    def _make_preview(item: dict) -> str:
        if item.get("type") == "image":
            return "    [Image]"
        text = item["text"]
        line = text.split("\n")[0].replace("\t", "  ")
        n_extra = len(text.splitlines()) - 1
        suffix = f"  [+{n_extra} lines]" if n_extra else ""
        return f"    {line[:61] + '…' if len(line) > 64 else line}{suffix}"

    def _apply_row_style(idx: int, selected: bool):
        if not (0 <= idx < len(current_rows)):
            return
        row, _content, xbtn = current_rows[idx]
        bg  = C["select_bg"] if selected else C["bg"]
        xfg = C["text"]      if selected else C["subtext"]
        row.config(bg=bg)
        for w in row.winfo_children():
            try:
                w.config(bg=bg)
            except Exception:
                pass
        xbtn.config(bg=bg, fg=xfg)

    def _set_selection(idx: int, scroll: bool = True):
        _apply_row_style(selected_idx[0], selected=False)
        selected_idx[0] = max(0, min(idx, len(current_rows) - 1)) if current_rows else 0
        _apply_row_style(selected_idx[0], selected=True)
        if scroll and current_rows:
            row = current_rows[selected_idx[0]][0]
            items_frame.update_idletasks()
            ry, rh = row.winfo_y(), row.winfo_height()
            fh, ch = items_frame.winfo_height(), list_canvas.winfo_height()
            top    = list_canvas.canvasy(0)
            if fh > 0 and rh > 0:
                if ry < top:
                    list_canvas.yview_moveto(ry / fh)
                elif ry + rh > top + ch:
                    list_canvas.yview_moveto((ry + rh - ch) / fh)

    def _load_thumbnail(path: str):
        """Return a Tk-compatible thumbnail. Uses PIL when available, falls back
        to Tk's native PhotoImage + subsample (PNG only, no extra deps)."""
        if HAS_PIL:
            img = Image.open(path)
            img.thumbnail((140, 90))
            return ImageTk.PhotoImage(img)
        raw = tk.PhotoImage(file=path)
        w_img, h_img = raw.width(), raw.height()
        scale = max(w_img // 140, h_img // 90, 1)
        return raw.subsample(scale, scale) if scale > 1 else raw

    def _add_row(i: int, item: dict):
        is_image = item.get("type") == "image"

        row = tk.Frame(items_frame, bg=C["bg"], cursor="hand2")
        row.pack(fill=tk.X)

        xbtn = tk.Label(row, text="×", bg=C["bg"], fg=C["subtext"],
                        font=("Sans Serif", 14), padx=10, pady=0, cursor="hand2")
        xbtn.pack(side=tk.RIGHT, anchor="center")

        if is_image:
            photo = None
            try:
                photo = _load_thumbnail(item["path"])
            except Exception:
                pass

            if photo is not None:
                _photo_refs.append(photo)
                content = tk.Label(row, image=photo, bg=C["bg"],
                                   padx=8, pady=6, anchor="w")
                content.pack(side=tk.LEFT, anchor="w")
            else:
                content = tk.Label(row, text=_make_preview(item),
                                   bg=C["bg"], fg=C["subtext"],
                                   font=("Monospace", 10), anchor="w", pady=7)
                content.pack(side=tk.LEFT, fill=tk.X, expand=True)
        else:
            content = tk.Label(row, text=_make_preview(item),
                               bg=C["bg"], fg=C["text"],
                               font=("Monospace", 10), anchor="w", pady=7)
            content.pack(side=tk.LEFT, fill=tk.X, expand=True)

        scroll_up   = lambda e: list_canvas.yview_scroll(-1, "units")
        scroll_down = lambda e: list_canvas.yview_scroll(+1, "units")

        for w in (row, content):
            w.bind("<Button-1>",        lambda e, _i=i: _set_selection(_i))
            w.bind("<Double-Button-1>", lambda e, _i=i: _do_paste(index=_i))
            w.bind("<Button-4>", scroll_up)
            w.bind("<Button-5>", scroll_down)

        xbtn.bind("<Enter>", lambda e: xbtn.config(fg=C["red"]))
        xbtn.bind("<Leave>", lambda e, _i=i:
                  xbtn.config(fg=C["text"] if selected_idx[0] == _i else C["subtext"]))
        xbtn.bind("<Button-1>", lambda e, _i=i: (_do_delete(_i), "break")[1])
        xbtn.bind("<Button-4>", scroll_up)
        xbtn.bind("<Button-5>", scroll_down)

        current_rows.append((row, content, xbtn))

    # ── Data operations ───────────────────────────────────────────────────────

    def _populate(source: list):
        nonlocal filtered_items, current_rows
        filtered_items = list(source)
        for w in items_frame.winfo_children():
            w.destroy()
        current_rows = []
        _photo_refs.clear()
        selected_idx[0] = 0
        count_var.set(f"{len(source)} items")
        for i, item in enumerate(source):
            _add_row(i, item)
        if source:
            _set_selection(0, scroll=False)

    def _do_clear_history():
        for item in items:
            if item.get("type") == "image":
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                except OSError:
                    pass
        save_history([])
        items.clear()
        search_var.set("")
        _filter()

    def _filter(*_):
        q = search_var.get().lower()
        if not q:
            _populate(items)
            return
        _populate([it for it in items
                   if it.get("type") != "image" and q in it["text"].lower()])

    def _do_paste(event=None, index: int | None = None):
        if index is None:
            index = selected_idx[0]
        if not filtered_items or index >= len(filtered_items):
            return
        item = filtered_items[index]
        if item.get("type") == "image":
            set_clipboard_image(item["path"], session)
        else:
            set_clipboard(item["text"], session)
        root.destroy()

    def _do_delete(index: int):
        if not filtered_items or index >= len(filtered_items):
            return
        item = filtered_items[index]
        if item.get("type") == "image":
            path = item.get("path")
            removed = False
            remaining = []
            for it in items:
                if not removed and it is item:
                    removed = True
                    continue
                remaining.append(it)
            if not any(it.get("type") == "image" and it.get("path") == path
                       for it in remaining):
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            h = item_hash(item)
            remaining = [it for it in items if item_hash(it) != h]
        save_history(remaining)
        items.clear()
        items.extend(remaining)
        _filter()
        if filtered_items:
            _set_selection(min(index, len(filtered_items) - 1))

    def _reload_history(_fd=None, _mask=None):
        """Reload history from disk when the history file changes (inotify callback)."""
        if _fd is not None:
            os.read(_fd, 4096)  # drain inotify events
        new_items = load_history()
        changed = (len(new_items) != len(items) or
                   (new_items and (not items or new_items[0] != items[0])))
        if changed:
            # _populate() destroys and recreates list widgets, which temporarily
            # shifts Tk focus and fires FocusOut on search_entry, causing the
            # border to flicker grey. Restore focus explicitly afterwards.
            focused = root.focus_get()
            items.clear()
            items.extend(new_items)
            _filter()
            if focused:
                focused.focus_set()

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def _on_key(event):
        keysym = event.keysym
        ctrl   = event.state & 0x4
        if keysym == "Escape" or (ctrl and keysym == "w"):
            root.destroy()
        elif keysym in ("Return", "KP_Enter"):
            _do_paste()
        elif keysym == "Delete":
            _do_delete(selected_idx[0])
        elif keysym == "Down" or (ctrl and keysym == "j"):
            _set_selection(selected_idx[0] + 1)
            return "break"
        elif keysym == "Up" or (ctrl and keysym == "k"):
            _set_selection(selected_idx[0] - 1)
            return "break"

    # ── Bindings ──────────────────────────────────────────────────────────────

    search_var.trace_add("write", _filter)
    root.bind("<Key>", _on_key)
    for seq in ("<Down>", "<Up>", "<Control-j>", "<Control-k>"):
        search_entry.bind(seq, _on_key)
    def _on_search_return(e=None):
        if search_var.get() == "/clear":
            _do_clear_history()
        else:
            _do_paste()
    search_entry.bind("<Return>", _on_search_return)
    search_entry.bind("<Escape>", lambda e: root.destroy())
    root.bind("<Control-w>", lambda e: root.destroy())

    clear_btn.bind("<Button-1>", lambda e: _do_clear_history())
    clear_btn.bind("<Enter>", lambda e: clear_btn.configure(fg=C["accent"]))
    clear_btn.bind("<Leave>", lambda e: clear_btn.configure(fg=C["subtext"]))

    # ── Start ─────────────────────────────────────────────────────────────────

    _populate(items)

    # Watch for history changes via inotify — no polling, no flickering.
    # save_history() uses os.replace(tmp → history.json), which is an atomic
    # rename. Renames fire IN_MOVED_TO on the parent directory, not
    # IN_CLOSE_WRITE on the file, so we watch the directory instead.
    from .config import HISTORY_FILE
    _inotify_fd = None
    _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    _ifd = _libc.inotify_init()
    if _ifd >= 0:
        IN_MOVED_TO = 0x00000080
        _libc.inotify_add_watch(_ifd, str(HISTORY_FILE.parent).encode(), IN_MOVED_TO)
        root.tk.createfilehandler(_ifd, tk.READABLE, _reload_history)
        _inotify_fd = _ifd

    def _cleanup_inotify():
        if _inotify_fd is not None:
            try:
                root.tk.deletefilehandler(_inotify_fd)
            except Exception:
                pass
            os.close(_inotify_fd)

    root.protocol("WM_DELETE_WINDOW", lambda: (_cleanup_inotify(), root.destroy()))

    def _grab_focus():
        root.lift()
        root.attributes("-topmost", True)
        search_entry.focus_set()
        root.after(200, lambda: root.attributes("-topmost", False))

    root.after(50, _grab_focus)
    root.mainloop()
