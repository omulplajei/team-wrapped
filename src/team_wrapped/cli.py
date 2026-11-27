"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scenes.build import BuildError, build
from .scenes.loader import LoadError
from .scenes.validate import format_report, resolve_and_validate


def _cmd_validate(args) -> int:
    root = Path(args.root)
    resolved = resolve_and_validate(args.script, root, root / args.data)
    print(format_report(resolved.report))
    return 0 if resolved.report.ok else 1


def _cmd_build(args) -> int:
    root = Path(args.root)
    try:
        result = build(args.script, root, root / args.data, root / args.out, theme=args.theme)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        if error.report is not None:
            print(format_report(error.report), file=sys.stderr)
        return 1
    for scene_id in result.skipped:
        print(f"skipped (unsupported): {scene_id}")
    print(f"built {result.index}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team-wrapped")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("validate-script", "check a script against the available data"),
        ("build", "build a self-contained HTML page for a script"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("script")
        p.add_argument("--root", default=".", help="repository root (default: current directory)")
        p.add_argument("--data", default="data", help="data folder under the root (data or data-sample)")
        if name == "build":
            p.add_argument("--out", default="dist", help="output folder under the root (default: dist)")
            p.add_argument("--theme", default=None, help="theme name")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-script":
            return _cmd_validate(args)
        return _cmd_build(args)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
