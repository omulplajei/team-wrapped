"""Command line entry point."""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from .aggregate import aggregate
from .collect import DEFAULT_OVERLAP_DAYS, collect, describe, describe_fetches, make_plan
from .collect.report import run_summary, status_report
from .config import load_config
from .derive import write_repos
from .github import GitHub
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


def _cmd_derive_repos(args) -> int:
    data_root = Path(args.root) / args.data
    config = load_config(data_root / "config.yml")
    path = write_repos(config, data_root)
    print(f"wrote {path}: {len(config.repos)} repositories, {len(config.groups)} groups")
    return 0


def _cmd_aggregate(args) -> int:
    try:
        written = aggregate(Path(args.root) / args.data, since=args.since, until=args.until)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}")
    return 0


def _cmd_collect(args) -> int:
    data_root = Path(args.root) / args.data
    config = load_config(data_root / "config.yml")
    plan = make_plan(config, args.repo, args.metric, args.since, args.until)
    if args.dry_run:
        now = datetime.datetime.now(datetime.timezone.utc)
        for line in describe(plan) + describe_fetches(data_root, plan, now, full=args.full,
                                                      overlap_days=args.overlap_days):
            print(line)
        print(f"dry run: {len(plan.repos)} repositories x {len(plan.metrics)} metrics, no API calls made")
        return 0
    result = collect(data_root, config, GitHub(max_requests=args.max_requests), plan, avatars=not args.no_avatars,
                     full=args.full, overlap_days=args.overlap_days)
    print()
    for line in run_summary(result, plan.metrics):
        print(line)
    return 1 if result.failed else 0


def _cmd_status(args) -> int:
    data_root = Path(args.root) / args.data
    for line in status_report(data_root, load_config(data_root / "config.yml")):
        print(line)
    return 0


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _days(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("--overlap-days must be 0 or more")
    return value


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
    derive = sub.add_parser("derive-repos", help="write derived/repos.json from the collection config")
    derive.add_argument("--root", default=".", help="repository root (default: current directory)")
    derive.add_argument("--data", default="data", help="data folder under the root (default: data)")
    agg = sub.add_parser("aggregate", help="write derived/*.json from data/raw")
    agg.add_argument("--root", default=".", help="repository root (default: current directory)")
    agg.add_argument("--data", default="data", help="data folder under the root (default: data)")
    agg.add_argument("--since", help="window start YYYY-MM-DD for this run (default: config since)")
    agg.add_argument("--until", help="window end YYYY-MM-DD for this run (default: config until)")
    col = sub.add_parser("collect", help="fetch GitHub activity into data/raw with gh (GraphQL)")
    col.add_argument("--root", default=".", help="repository root (default: current directory)")
    col.add_argument("--data", default="data", help="data folder under the root (default: data)")
    col.add_argument("--repo", action="append", help="only this repository (repeatable)")
    col.add_argument("--metric", action="append", help="only this metric (repeatable)")
    col.add_argument("--since", help="window start YYYY-MM-DD for this run (default: config since)")
    col.add_argument("--until", help="window end YYYY-MM-DD for this run (default: config until)")
    col.add_argument("--max-requests", type=_positive, help="stop cleanly after N gh calls")
    col.add_argument("--no-avatars", action="store_true", help="do not download avatars")
    col.add_argument("--dry-run", action="store_true", help="print the plan and make no API calls")
    col.add_argument("--full", action="store_true",
                     help="ignore the checkpoints and fetch the whole window (new checkpoints are still written)")
    col.add_argument("--overlap-days", type=_days, default=DEFAULT_OVERLAP_DAYS,
                     help=f"days before the last covered commit time fetched again (default: {DEFAULT_OVERLAP_DAYS})")
    stat = sub.add_parser("status", help="show per repo and metric collection status (no network)")
    stat.add_argument("--root", default=".", help="repository root (default: current directory)")
    stat.add_argument("--data", default="data", help="data folder under the root (default: data)")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            return _cmd_collect(args)
        if args.command == "status":
            return _cmd_status(args)
        if args.command == "aggregate":
            return _cmd_aggregate(args)
        if args.command == "derive-repos":
            return _cmd_derive_repos(args)
        if args.command == "validate-script":
            return _cmd_validate(args)
        return _cmd_build(args)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
