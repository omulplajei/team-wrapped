# team-wrapped: data design

Date: 2026-11-25
Status: draft, pending review
Scope of this document: **data only** (what is collected, stored and derived). Presentation is out of scope.

## 1. Purpose

A generic, public tool that collects GitHub activity for a set of repositories and derives statistics a front-end can present. Everything specific to the user's project (org, repos, groups, bot patterns) lives in a private, git-ignored `data/` folder. A `data-sample/` folder with dummy data lets others try the tool and see the expected layout.

The emphasis is on **what the repos delivered**, not on individuals. Everyone's activity is included, including one-off contributors.

## 2. Decisions

| Topic | Decision |
|---|---|
| Source | GitHub API through the `gh` CLI (`gh api`), no token handling in our code |
| Language | Python 3.11+; dependencies: PyYAML, pytest |
| Architecture | Two-stage file pipeline: `collect` writes raw JSONL, `aggregate` writes derived JSON |
| Metrics collected now | commits, pull requests, reviews, comments. Pluggable so more can be added later |
| People | Everyone, including bots (flagged, not dropped) and one-off contributors |
| Time range | Configurable `since`/`until`; default is full history |
| Grouping | Generic named groups of repos in private config. Capability statistics are per-group aggregates and only exist if groups are configured |
| Collection | Multi-pass: resumable, incremental, idempotent, request-budgeted |

Typical use: a team lists the repos it owns and defines one group per area of ownership. That mapping lives only in the private `data/config.yml`, and nothing project-specific is committed.

## 3. Repository layout

```
team-wrapped/
  src/team_wrapped/
    cli.py                # collect, aggregate, status
    config.py             # load and validate data/config.yml
    github.py             # gh api wrapper: pagination, retry, rate limits
    checkpoint.py         # per repo + metric sync state
    contributors.py       # contributor registry and avatar download
    metrics/              # one plugin per metric
      base.py             # Metric interface
      commits.py  pull_requests.py  reviews.py  comments.py
    aggregate/            # one module per statistic family
      delivery_volume.py  review_collab.py  summary.py  curiosities.py
    metadata.py           # builds data/derived/meta.json
  data/                   # GIT-IGNORED: config.yml, raw/, derived/, avatars/
  data-sample/            # same layout, dummy repos and records
  tests/
  docs/superpowers/specs/
```

`.gitignore` contains `data/`. A CI check fails if anything under `data/` is tracked.

## 4. Configuration (`data/config.yml`)

| Key | Meaning |
|---|---|
| `org` | GitHub org or owner |
| `repos` | list of repo names |
| `groups` | optional map of group name to repo names. Enables capability statistics |
| `since`, `until` | optional window; default is full history |
| `metrics` | enabled metrics, for example `[commits, pull_requests, reviews, comments]` |
| `commit_branches` | `default` (default) or `all` |
| `bot_patterns` | login patterns marking bots, for example `*[bot]` |
| `aliases` | optional map merging several logins or emails into one contributor |
| `timezone` | used for weekday and hour statistics; default UTC |
| `curiosities.top_n` | records kept per curiosity; default 5 |
| `avatars.download` | download contributor avatars (default `true`) |
| `reviewer_pairs` | author-to-reviewer pair statistic; default `false` |

`data-sample/config.yml` documents every option. Bad config (unknown metric, malformed dates, empty repo list) fails at startup with a clear message.

## 5. Raw records

Stored as JSON-lines at `data/raw/<repo>/<metric>.jsonl`. Records are keyed by `(repo, metric, id)`; re-fetching overwrites and never duplicates. Records for cheap-pass and enrichment-pass data carry an `enriched` flag.

| Metric | Fields |
|---|---|
| **commit** | repo, sha, author login (nullable), author name, author email, authored and committed timestamps, `is_merge`, linked PR number if known. Enriched: additions, deletions, files changed |
| **pull_request** | repo, number, author login, created, merged, closed, state, base branch, labels, draft, comment count, review count. Enriched: commit count, changed files, additions, deletions |
| **review** | repo, PR number, reviewer login, state (approved, changes requested, commented), submitted timestamp |
| **comment** | repo, PR number, author login, kind (review comment on code, or conversation comment), created timestamp, `comment_id`, `in_reply_to_id`, `thread_root_id` |

Bot tagging (`is_bot`) is applied by the aggregate step from `bot_patterns`, so changing the patterns never needs re-collection.

### Metric plugin interface

A plugin declares its `name`, a `fetch(repo, since, checkpoint)` generator that yields raw records, a record schema, and a `checkpoint_key`. The registry discovers plugins in `metrics/`, and config enables them. Adding a metric means adding one file and one config entry.

## 6. Contributor registry

Built during collection from the author fields of all four metrics and deduplicated across all repos. Written to `data/derived/contributors.json`.

The purpose is to show **how many contributors there are**, not to profile individuals. No per-person activity counts are stored.

**Fields per contributor:** stable id, `login` (nullable), display name if known, `avatar_file` (path in `data/avatars/`), `kind` (`human`, `bot` or `unlinked`), the repos and groups they touched, first and last activity dates.

**Unlinked commit authors.** A commit author whose email is not tied to a GitHub account has no login and no avatar. These are counted as contributors:
- Identity key: the author email if present, otherwise the author name. Matching `aliases` merge them into a linked contributor.
- `kind` is `unlinked`, and the avatar is a shared placeholder.
- The email is never written to `derived/`. The id is a hash of the key. The raw commit files keep the email, since they are git-ignored.

**Counts in the output.** Total contributors, with the breakdown human, bot and unlinked, overall, per group and per repo. Consumers that want a "humans only" total can exclude bots.

**Avatars.** On by default (`avatars.download`). Each linked contributor's avatar (`https://github.com/<login>.png`) is downloaded once into `data/avatars/<login>.png` and reused on later passes. Deleted accounts (`ghost`) get the default avatar. A failed download falls back to the placeholder and is recorded in `meta.json`. Only public profile data is stored.

## 7. Derived statistics

All statistics come from raw records. Each belongs to one metric, so disabling a metric disables its statistics, and the metadata notes which were skipped. Every statistic can be sliced by **time bucket** (day, week, month, quarter, year) and by **scope** (one repo, one group, all repos). Group scope only exists when groups are configured.

### 7.1 Delivery volume (commits and pull requests)
- Commits per bucket, split into merge and non-merge
- Lines added, lines deleted, net lines, files changed per bucket (needs enrichment)
- PRs opened and merged per bucket
- Merged-PR size distribution: lines changed, files changed, commit count (needs enrichment)

### 7.2 Review and collaboration (reviews and comments)
- Reviews and review comments per bucket
- Review outcome mix (approved, changes requested, commented)
- Review comments per PR, and review rounds per PR
- Review load: reviews per reviewer, kept aggregate (distribution, not a named ranking)
- Author-to-reviewer pairs: optional, off by default (`reviewer_pairs`)

Review statistics count non-author activity only.

### 7.3 Overall and period summaries
- Totals for the configured window
- Period-over-period change (this quarter against the last, and similar)
- Busiest and quietest periods
- Activity by weekday and hour, in the configured timezone

### 7.4 Curiosities
Top-N records per scope. Each record holds the value, the repo and the PR or commit reference. N is `curiosities.top_n`, and each curiosity can be toggled.

| Curiosity | Source |
|---|---|
| Longest comment chain (longest code-review thread) | comment `thread_root_id` / `in_reply_to_id` |
| PR with the most comments (both kinds) | comments grouped by PR |
| PR with the most commits | `commit_count` (enriched) |
| PR with the most files modified | `changed_files` (enriched) |
| Biggest PR by lines changed | additions + deletions (enriched) |
| PR with the most reviews | reviews grouped by PR |
| Longest-lived PR | PR created to merged or closed |
| Most review rounds on one PR | changes-requested reviews followed by new commits |
| Biggest single commit (lines, files) | commit stats (enriched) |
| Busiest day (commits, merged PRs) | timestamps |

"Longest chain" means a code-review thread, because conversation comments on a PR are flat. Curiosities that depend on enriched records are computed from enriched records only and labelled partial in `meta.json` until coverage is complete.

### 7.5 Capability statistics (optional)
Not a separate family. Where `groups` is configured, every statistic above is also produced per group. With no groups, only per-repo and overall scopes are produced.

## 8. Collection and multi-pass behaviour

Collection is expected to take several passes because of API rate limits.

- **Two tiers per metric.** The cheap pass uses list endpoints only. The enrichment pass makes per-PR and per-commit detail calls (one call each) for commit count, changed files, additions, deletions and commit stats. A run does the cheap pass for all repos before any enrichment, so usable data exists early. `--enrich-only` and `--no-enrich` select the tier.
- **Resumable.** Checkpoints are written after each page or batch, so a killed run loses at most one batch. The checkpoint swap is atomic.
- **Idempotent.** Records are keyed so re-fetching never duplicates.
- **Incremental.** Later runs fetch only data newer than the checkpoint. Open PRs are re-fetched each run because their state changes.
- **Budgeted.** `collect --max-requests N` stops cleanly at the budget. `gh api rate_limit` is checked up front. When the limit is hit the run sleeps or exits with a "resume after HH:MM" message.
- **Filters.** `collect [--repo X] [--metric Y]`.

### CLI
- `collect`: fetch raw data, contributor registry and avatars
- `aggregate`: build `data/derived/`
- `status`: per repo and metric, shows complete, partial, never-run or failed, with last sync and coverage dates

## 9. Metadata (`data/derived/meta.json`)

Read by a front-end to show freshness and gaps.

- Last sync time per repo and metric
- Coverage window per repo and metric
- Status per repo and metric: complete, partial, never-run, failed, with reason and error count
- Enrichment coverage (enriched records over total)
- Skipped statistics (disabled metric) and partial statistics (incomplete enrichment)
- Skipped corrupt JSONL lines, failed avatar downloads
- Config window and the generation time

## 10. Error handling

- **Isolation.** Failures are isolated per repo and metric. A 404 or 403 on one repo is recorded as `failed` with the reason, and the rest continues.
- **Retries.** Transient errors (5xx, secondary rate limits) retry with backoff. After the retry limit, that unit is marked `partial`.
- **Storage.** Corrupt or half-written JSONL lines are skipped on read and reported in the metadata. Writes are append-only.
- **Contributors.** A missing login falls back to the unlinked identity. A failed avatar download falls back to the placeholder.

## 11. Testing

- Unit tests: config loader, checkpoint logic, bot filtering, aliases, contributor identity (linked, unlinked, alias merge).
- Metric plugins are tested against recorded `gh api` JSON fixtures with the `github.py` wrapper mocked. No network access.
- Aggregators are tested as pure functions on small hand-built record sets: empty windows, partial enrichment, disabled metrics.
- Curiosity tests: ties, missing enrichment, comment-thread reconstruction.
- Contributor tests: counts by kind, email never present in `derived/`, avatar failure fallback.
- End-to-end test: `aggregate` on `data-sample/` compared with a snapshot, which also keeps the sample valid.
- CI check: fails if `data/` or any file containing real repo names is tracked.

## 12. Out of scope (for now)

- Presentation and front-end
- Delivery speed (time to merge, time to first review), contributor footprint statistics and repo comparison tables. They can be added later as aggregate modules because the raw data already supports them
- Issues, releases and CI workflow metrics (the plugin interface allows them later)
- Per-person leaderboards
- A helper that generates groups from org-config. This would be an optional private script outside the generic core
