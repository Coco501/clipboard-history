"""Command-line entry point — parses arguments and dispatches subcommands."""

import argparse
import sys

from .daemon import cmd_daemon
from .storage import save_history
from .ui import cmd_show


def cmd_clear() -> None:
    save_history([])
    print("Clipboard history cleared.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lightweight clipboard history manager for Linux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  clipboard-history daemon   # start background monitor\n"
            "  clipboard-history show     # open picker (auto-starts daemon)\n"
            "  clipboard-history clear    # wipe all history\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("daemon", help="Run the background clipboard monitor")
    sub.add_parser("show",   help="Open the history picker popup")
    sub.add_parser("clear",  help="Clear all stored history")

    args = parser.parse_args()

    if args.cmd == "daemon":
        cmd_daemon()
    elif args.cmd == "show":
        cmd_show()
    elif args.cmd == "clear":
        cmd_clear()
    else:
        parser.print_help()
        sys.exit(1)
