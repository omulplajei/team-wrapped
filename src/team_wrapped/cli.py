"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scenes.loader import LoadError
from .scenes.validate import format_report, resolve_and_validate


def _cmd_validate(args) -> int:
    root = Path(args.root)
    resolved = resolve_and_validate(args.script, root, root / args.data)
    print(format_report(resolved.report))
    return 0 if resolved.report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team-wrapped")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-script", help="check a script against the available data")
    validate.add_argument("script")
    validate.add_argument("--root", default=".", help="repository root (default: current directory)")
    validate.add_argument("--data", default="data", help="data folder under the root (data or data-sample)")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-script":
            return _cmd_validate(args)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
