"""Plain-text tables for `collect` and `status`."""
from __future__ import annotations

from pathlib import Path

from ..aggregate.raw import load_raw
from .checkpoint import read_checkpoints
from .store import read_details


def table(header: list, rows: list) -> list:
    widths = [max(len(str(row[i])) for row in [header, *rows]) for i in range(len(header))]
    return ["  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip()
            for row in [header, *rows]]


def run_summary(result, metrics) -> list:
    """repo x metric table of one run: status and records fetched."""
    cells = {(u.repo, u.metric): u.status if u.status in ("not run", "failed") else f"{u.status} ({u.records})"
             for u in result.units}
    repos = list(dict.fromkeys(u.repo for u in result.units))
    lines = table(["repo", *metrics], [[repo, *(cells.get((repo, m), "-") for m in metrics)] for repo in repos])
    lines.append(f"requests: {result.requests}")
    if result.avatars_failed:
        lines.append(f"avatars failed (placeholder used): {', '.join(result.avatars_failed)}")
    return lines


def status_report(data_root, config) -> list:
    """repo x metric table from status.json and the record counts on disk, plus reasons and last collection."""
    data_root = Path(data_root)
    raw = load_raw(data_root, config)
    counts = {}
    for metric, records in raw.records.items():
        for record in records:
            counts[(record["repo"], metric)] = counts.get((record["repo"], metric), 0) + 1
    rows, notes = [], []
    for repo in config.repos:
        details = read_details(data_root / "raw" / repo)
        row = [repo]
        for metric in config.metrics:
            state = raw.status[repo][metric]
            row.append(state if state in ("never-run", "failed") else f"{state} ({counts.get((repo, metric), 0)})")
            detail = details.get(metric) if isinstance(details.get(metric), dict) else {}
            if detail.get("reason"):
                notes.append(f"{repo} {metric}: {detail['reason']}")
        times = [d.get("collected_at") for d in details.values() if isinstance(d, dict) and d.get("collected_at")]
        row.append(f"last collected {max(times)}" if times else "")
        rows.append(row)
    lines = table(["repo", *config.metrics, ""], rows)
    if raw.corrupt:
        lines.append("corrupt lines skipped: " + ", ".join(f"{k} ({v})" for k, v in sorted(raw.corrupt.items())))
    return lines + notes + checkpoint_report(data_root, config)


def _minute(moment) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def checkpoint_report(data_root, config) -> list:
    """Per repository, the last sync and covered range of each metric's checkpoint (UTC). Neighbouring metrics
    with the same checkpoint share a row, so pull requests, reviews and comments usually take one."""
    rows, notes = [], []
    for repo in config.repos:
        checkpoints, warnings = read_checkpoints(Path(data_root) / "raw" / repo)
        notes += [f"{repo}: {warning}" for warning in warnings]
        groups = []
        for metric in config.metrics:
            entry = checkpoints.get(metric)
            if entry is None:
                continue
            if groups and groups[-1][1] == entry:
                groups[-1][0].append(metric)
            else:
                groups.append(([metric], entry))
        for metrics, entry in groups:
            covered = f"{entry.since or 'beginning'} .. {_minute(entry.covered_to)}"
            rows.append([repo, ", ".join(metrics), _minute(entry.synced_at), covered])
    if not rows:
        return ["", "checkpoints: none yet (the next collect fetches in full)", *notes]
    return ["", "checkpoints (UTC; the next collect fetches only what changed since)",
            *table(["repo", "metrics", "last sync", "covered"], rows), *notes]
