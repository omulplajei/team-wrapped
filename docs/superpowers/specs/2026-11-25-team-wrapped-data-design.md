# team-wrapped: data design

Date: 2026-11-25
Status: draft, pending review
Scope of this document: what is collected, stored and derived (sections 1 to 11), how scenes and scripts are defined (section 12), and how a script is played in a web page (section 13). Visual design details (colours, typography, layouts) are not specified here.

## 1. Purpose

A generic, public tool that collects GitHub activity for a set of repositories and derives statistics a front-end can present. Everything specific to the user's project (org, repos, groups, bot patterns) lives in a private, git-ignored `data/` folder. A `data-sample/` folder with dummy data lets others try the tool and see the expected layout.

The emphasis is on **what the repos delivered**, not on individuals. Everyone's activity is included, including one-off contributors.

## 2. Decisions

| Topic | Decision |
|---|---|
| Source | GitHub GraphQL API through the `gh` CLI (`gh api graphql`), no token handling in our code |
| Language | Python 3.11+; dependencies: PyYAML, pytest |
| Architecture | Two-stage file pipeline: `collect` writes raw JSONL, `aggregate` writes derived JSON |
| Metrics collected now | commits, pull requests, reviews, comments. Pluggable so more can be added later |
| People | Everyone, including bots (flagged, not dropped) and one-off contributors |
| Time range | Configurable `since`/`until`; default is full history |
| Grouping | Generic named groups of repos in private config. Capability statistics are per-group aggregates and only exist if groups are configured |
| Collection | Multi-pass: resumable per repo and metric, idempotent, request-budgeted (incremental fetching deferred) |

Typical use: a team lists the repos it owns and defines one group per area of ownership. That mapping lives only in the private `data/config.yml`, and nothing project-specific is committed.

## 3. Repository layout

```
team-wrapped/
  src/team_wrapped/
    cli.py                # collect, status, aggregate, derive-repos, validate-script, build
    config.py             # load and validate data/config.yml
    github.py             # gh api graphql wrapper: error classification, retry, rate limits, request budget
    collect/              # the collect stage
      __init__.py         # plan (filters, window), units per repo + metric, statuses
      queries.py          # every GraphQL document
      commits.py          # default-branch history, stats included
      pull_requests.py    # PR search with reviews, comments and review threads
      avatars.py          # avatar download (file names shared with aggregate/contributors.py)
      store.py  report.py # raw writes (merge by key, atomic), status tables
    aggregate/            # one module per statistic family, plus raw.py (loader), contributors.py, meta.py
    scenes/               # script loading, validate-script, build
  web/                    # front-end (public)
    player/               # page template, playback controller, controls, styles
    scene-types/          # one folder per scene type: type.yml + render.js
    presets/              # shared animation presets
    vendor/               # vendored GSAP, with its licence text
  scenes/                 # shared scene definitions (public)
  scripts/                # shared scripts (public), for example year-wrapped
  dist/                   # GIT-IGNORED: built pages, one folder per script
  data/                   # GIT-IGNORED: config.yml, raw/, derived/, avatars/,
                          #   scenes/ and scripts/ (private), assets/
  data-sample/            # dummy data only: config, raw records, derived output
  tests/
  docs/
    datasets.md           # dataset catalog: the contract between data and scenes
    superpowers/specs/
```

`.gitignore` contains `data/` and `dist/` (built pages embed real data). A CI check fails if anything under `data/` or `dist/` is tracked.

## 4. Configuration (`data/config.yml`)

| Key | Meaning |
|---|---|
| `org` | GitHub org or owner |
| `repos` | list of repo names |
| `groups` | optional map of group name to repo names. Enables capability statistics |
| `group_info` | optional map of group name to `{label, category}`. `label` is the display name (default: the group name); `category` is `core`, `extension` or `support` (default: none, drawn neutral). Keys must be configured groups; unknown fields are rejected |
| `since`, `until` | optional window; default is full history |
| `metrics` | enabled metrics, for example `[commits, pull_requests, reviews, comments]` |
| `commit_branches` | `default` (default) or `all` |
| `bot_patterns` | login patterns marking bots, for example `*[bot]` |
| `aliases` | optional map merging several logins or emails into one contributor |
| `timezone` | used for weekday and hour statistics; default UTC |
| `curiosities.top_n` | records kept per curiosity; default 5 |
| `avatars.download` | download contributor avatars (default `true`) |
| `reviewer_pairs` | author-to-reviewer pair statistic; default `false` |

The loader (`config.py`) validates `org`, `repos`, `groups`, `since`, `until`, `metrics`, `bot_patterns`, `aliases`, `timezone`, `curiosities.top_n` and `avatars.download`; `commit_branches` (`default` or `all`; `collect` supports only `default` for now and stops with a message on `all`) is validated too, and `reviewer_pairs` is accepted and validated when a statistic uses it. In `bot_patterns`, `*` and `?` are wildcards and every other character, brackets included, is literal, so `*[bot]` matches `renovate[bot]` and not `ken-t`.

`data-sample/config.yml` documents every option. Bad config (unknown metric, malformed dates, empty repo list) fails at startup with a clear message.

## 5. Raw records

Stored as JSON-lines at `data/raw/<repo>/<metric>.jsonl`. Records are keyed by `(repo, metric, id)`; re-fetching overwrites and never duplicates. Records carry an `enriched` flag; the GraphQL collector writes commits and pull requests already enriched (section 8).

| Metric | Fields |
|---|---|
| **commit** | repo, sha, author login (nullable), author name, author email, authored and committed timestamps, `is_merge`, linked PR number if known. Enriched: additions, deletions, files changed |
| **pull_request** | repo, number, author login, created, merged, closed, state, base branch, labels, draft, comment count, review count. Enriched: commit count, changed files, additions, deletions |
| **review** | repo, PR number, reviewer login, state (approved, changes requested, commented), submitted timestamp |
| **comment** | repo, PR number, author login, kind (review comment on code, or conversation comment), created timestamp, `comment_id`, `in_reply_to_id`, `thread_root_id` |

Bot tagging (`is_bot`) is applied by the aggregate step from `bot_patterns`, so changing the patterns never needs re-collection.

### 5.1 Raw file format (the contract between `collect` and `aggregate`)

One JSON object per line. Timestamps are ISO 8601 UTC strings (`2026-03-14T09:30:00Z`). Field names are exactly:

| File | Fields (`?` = absent until enriched) |
|---|---|
| `commits.jsonl` | `repo`, `sha`, `author_login` (null when unlinked), `author_name`, `author_email`, `authored_at`, `committed_at`, `is_merge`, `pr_number` (null if unknown), `enriched` (bool), `additions?`, `deletions?`, `files_changed?` |
| `pull_requests.jsonl` | `repo`, `number`, `author_login`, `created_at`, `merged_at` (null), `closed_at` (null), `state` (`open`, `closed`, `merged`), `base_branch`, `labels`, `draft`, `comment_count`, `review_count`, `enriched` (bool), `commit_count?`, `changed_files?`, `additions?`, `deletions?` |
| `reviews.jsonl` | `repo`, `pr_number`, `review_id?`, `reviewer_login`, `state` (`approved`, `changes_requested`, `commented`), `submitted_at` |
| `comments.jsonl` | `repo`, `pr_number`, `author_login`, `kind` (`review` for code comments, `conversation`), `created_at`, `comment_id`, `in_reply_to_id` (null), `thread_root_id` (null for conversation comments) |
| `status.json` (one per repo) | `{"<metric>": "complete" | "partial" | "never-run" | "failed"}`. A missing file means every metric is `never-run`; a metric missing from an existing file whose jsonl exists counts as `complete` |

Layout: `data/raw/<repo>/<file>`. The aggregator never writes to `raw/`.

Keys and repeated records. Files are append-only (section 10), so a file may hold the same key more than once, for example a cheap commit record followed by its enriched version. The aggregator keeps the last record per key (first-seen order is kept, so output stays deterministic): commits by (`repo`, `sha`), pull requests by (`repo`, `number`), comments by (`repo`, `comment_id`), reviews by (`repo`, `review_id`). A review record without `review_id` falls back to (`pr_number`, `reviewer_login`, `submitted_at`, `state`). A record whose key field is missing or of the wrong type (`sha` text, `number` and `pr_number` whole numbers, `comment_id` and `review_id` whole number or text) is skipped and counted as a corrupt line.

### 5.2 Aggregator v1 scope

`aggregate` produces what the shipped scenes read: `summary.totals`, `delivery_volume.lines`, the curiosity datasets listed in `docs/datasets.md`, `contributors`, `repos.touched`, and `meta.json`. Scopes are `all` and `group:<name>` (plus `commit_flow`, which has only `all`); `repo:<name>` scopes, time buckets and `review_collab` are deferred until a scene needs them. All statistics respect the configured window (`since`/`until`, inclusive, evaluated in the configured `timezone`) and `metrics`.

### Metric plugin interface

A plugin declares its `name`, a `fetch(repo, since, checkpoint)` generator that yields raw records, a record schema, and a `checkpoint_key`. The registry discovers plugins in `metrics/`, and config enables them. Adding a metric means adding one file and one config entry.

## 6. Contributor registry

Built during collection from the author fields of all four metrics and deduplicated across all repos. Written to `data/derived/contributors.json`.

The purpose is to show **how many contributors there are**, not to profile individuals. No per-person activity counts are stored.

**Fields per contributor:** stable id, `login` (nullable), display name if known, `avatar_file` (path in `data/avatars/`), `kind` (`human`, `bot` or `unlinked`), the repos and groups they touched, first and last activity dates.

**Unlinked commit authors.** A commit author whose email is not tied to a GitHub account has no login and no avatar. These are counted as contributors:
- Identity key: the author email if present, otherwise the author name. Keys are type-prefixed (`login:`, `email:`, `name:`), so an unlinked author named like a login never merges into that login. `aliases` map an alias to a canonical login (an alias that is a login, or an email for a record that has no login) and merge the unlinked author into the linked contributor.
- `kind` is `unlinked`, and the avatar is a shared placeholder.
- The email is never written to `derived/`. The id is sequential (`c001`, `c002`, ...), assigned after the deterministic sort (kind, login, key); nothing in it is derived from the email or name. The raw commit files keep the email, since they are git-ignored.

**Counts in the output.** Total contributors, with the breakdown human, bot and unlinked, overall, per group and per repo. Consumers that want a "humans only" total can exclude bots.

**Avatars.** On by default (`avatars.download`). Each linked contributor's avatar (`https://github.com/<login>.png`) is downloaded once by `collect` into `data/avatars/<name>.png` (`name` is the lower-cased login with characters other than letters, digits, `.`, `_` and `-` replaced, so `dependabot[bot]` is `dependabot_bot`) and reused on later passes. Deleted accounts (`ghost`) get the default avatar. A failed download falls back to the placeholder and is recorded in `data/raw/avatars-failed.json` (section 8). Only public profile data is stored.

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
Top-N records per scope, best first. Each record holds the value and what locates it: the repo and a PR number or commit, a date or month, or a date range. N is `curiosities.top_n`, and each curiosity can be toggled.

| Curiosity | Source |
|---|---|
| Longest comment chain (longest code-review thread) | comment `thread_root_id` / `in_reply_to_id` |
| PR with the most comments (both kinds) | comments grouped by PR |
| PR with the most commits | `commit_count` (enriched) |
| PR with the most files modified | `changed_files` (enriched) |
| Biggest PR by lines changed | additions + deletions (enriched) |
| PR with the most reviews | reviews grouped by PR |
| Longest-lived PR | PR created to merged or closed |
| Most review rounds on one PR (rounds = changes-requested reviews on one PR) | reviews with state `changes_requested`, grouped by PR |
| Biggest single commit (lines, files) | commit stats (enriched) |
| Busiest day (commits, merged PRs) | timestamps |
| Busiest month (commits per month) | timestamps |
| Longest commit streak (consecutive days) | commit timestamps |
| Longest merge streak (consecutive days) | merged PR timestamps |
| Most lines deleted in one PR | `deletions` (enriched) |

"Longest chain" means a code-review thread, because conversation comments on a PR are flat. Curiosities that depend on enriched records are computed from enriched records only and labelled partial in `meta.json` until coverage is complete.

### 7.5 Capability statistics (optional)
Not a separate family. Where `groups` is configured, every statistic above is also produced per group. With no groups, only per-repo and overall scopes are produced.

### 7.6 Derived file format

`aggregate` writes one JSON file per dataset family to `data/derived/<family>.json`. The files are what scenes, and any front-end, read. `data-sample/derived/` shows a worked example.

```json
{
  "period": {"since": "2026-01-01", "until": "2026-12-31"},
  "scopes": {
    "all":         { "<dataset>": { ... } },
    "group:alpha": { "<dataset>": { ... } },
    "repo:my-repo": { "<dataset>": { ... } }
  }
}
```

- **Files.** `summary.json`, `delivery_volume.json`, `review_collab.json`, `curiosities.json`, `commit_flow.json` (section 7.7), `contributors.json` and `repos.json`, plus `meta.json` (section 9).
- **Scopes.** Keys are `all`, `group:<name>` and `repo:<name>`. `group:*` keys exist only when groups are configured. Every file has the same scope keys, except families that define only `all` (`commit_flow`).
- **Dataset names.** A dataset name `family.name` (for example `delivery_volume.lines`) resolves to `<family>.json`, then `scopes[<scope>][name]`. The `contributors` dataset has no second part, so it resolves to `scopes[<scope>]` itself.
- **Field paths.** A field such as `total_net` is a key of the dataset object. A path such as `list.kind` means the key `kind` on the items of the list `list`. A field that is absent on some items (for example `list.login` on unlinked contributors) counts as present if any item has it.
- **Time-bucketed datasets.** These hold one series per bucket size, keyed `day`, `week`, `month`, `quarter` or `year`. Each series is a list of `{"start": "<date>", ...fields}` entries ordered by `start`. The sample data does not exercise this shape yet, so it will be confirmed by the first scene that needs a time series.
- **Curiosities.** Each dataset is a list of up to `top_n` records, best first (sorted by `value`, descending). A record holds `value` and, depending on the curiosity, `repo`, `pr_number`, `sha`, `files`, `date`, `month`, `from`, `to` or `merged_prs`. Records never carry people or PR titles. A dataset is empty (or absent) when there is nothing to report: records with a `value` of 0 or null fields are never written. Every record carries all the fields of its row. Dates and months are calendar dates in the configured time zone.
- **Repositories touched.** `repos.json` holds `touched` with `total` and `list` (items `{"name": ...}`) per scope. A repository is touched when it has at least one commit (author date), pull request (created or merged date), review (submitted date) or comment (created date) inside the window, from any author including bots, among the enabled metrics. `total` equals the length of `list`, and `list` is ordered alphabetically by `name`. The dataset is partial when any in-scope repository's status for an enabled metric is not complete. An empty list counts as missing data for scenes that require `list.name`, so scripts mark such scenes `on_missing_data: skip`. Until the aggregator exists, `derive-repos` writes this file from the configured `repos` and `groups` (every configured repository counts as touched) and marks it with `"basis": "configuration"`.
- **Paths to files.** `avatar_file` is relative to the data root (`data/` or `data-sample/`).
- **Privacy.** Derived files never contain author emails (section 6).
- **Metadata.** `meta.json` has no `scopes`. It holds `generated_at`, `period`, per-repo and per-metric `status`, `enrichment_coverage`, `partial_datasets` and the resolved `groups`.
- **Partial datasets.** A dataset named in `meta.json`'s `partial_datasets` was computed from incomplete data. Scenes that set `allow_partial: false` treat it as unsupported.

### 7.7 Commit flow

`commit_flow.json` feeds the scene that drops one year of commits, as blocks sized by lines changed, into one hexagon per capability. Scope `all` only; the datasets are `groups` (a list with one record per configured group, in config order: `name`, `label`, `category` when set, `total`, and `commits` as `[day, lines]` pairs) and `window` (`days`, `start`). `day` counts whole local calendar days in the configured timezone since the window start; `lines` is additions plus deletions, 0 for an unenriched commit. Merge commits and commits outside the window are skipped, a repository in several groups counts in each, and commits are ordered by day, authored timestamp, then sha so output is deterministic. The window needs both `since` and `until`; without them (or without groups) the family is written empty and scenes that require it fail validation or are skipped. The dataset is partial when an in-scope non-merge commit is not enriched or a grouped repository's commits status is not complete. The file holds no author, message or hash. The writer prints each pair on its own line to keep a year of commits small.

## 8. Collection and multi-pass behaviour

Collection may take several passes because of API rate limits.

- **One transport.** Every call is `gh api graphql` (`github.py`); the documents are in `collect/queries.py`. `gh` holds the credentials (`gh auth login`); our code never sees a token.
- **No separate enrichment pass (v1).** GraphQL returns commit stats (`additions`, `deletions`, `changedFilesIfAvailable`) with the history page and pull request sizes (`commits.totalCount`, `changedFiles`, `additions`, `deletions`) with the search page, so records are written with `enriched: true`. A commit whose `changedFilesIfAvailable` is null is written with `enriched: false` and no stats.
- **Commits.** The default branch history (`commit_branches: default`; `all` is rejected until supported), filtered with `since`/`until` on the commit date. `is_merge` is more than one parent; `pr_number` is the first associated pull request. A commit author without a linked user is unlinked (`author_login` null, name and email kept in raw), unless the email is a GitHub noreply address, whose login is used (this links bot commits such as `…+dependabot[bot]@users.noreply.github.com`).
- **Pull requests, reviews, comments.** One search per repository: `repo:<org>/<repo> is:pr sort:created-asc created:<=<end> updated:>=<start>`. Search returns at most 1000 results per query, so a larger result splits the `updated` range in halves recursively; a range under a minute that still exceeds 1000 is kept at 1000 and marked partial. Reviews, conversation comments and review threads (with their comments) are inlined in the search page, and longer connections are completed with `node(id:)` follow-ups. `comment_count` is conversation comments plus review comments. Dismissed and pending reviews are skipped. A review comment's `thread_root_id` is the first comment of its thread and `in_reply_to_id` its `replyTo`. GraphQL returns a bot's login without `[bot]`; the collector appends it so `bot_patterns` match. A deleted account has a null login.
- **Window.** `since`/`until` (or `collect --since/--until` for one run) are local dates in `timezone`, sent as the UTC instants of local midnight starting `since` and the last second of `until`. The aggregator applies the exact window again.
- **Units and checkpoints.** A unit is one repository and metric (pull requests, reviews and comments share one search). When a unit ends its records are merged into the jsonl by key (atomic temporary file and rename) and `status.json` is updated: `complete`, `partial` (rate limit, budget, retries exhausted, capped search) or `failed` (missing or forbidden repository, rejected query; nothing written). Reasons, the collection time, record count and window go to `status-detail.json`, which the aggregator ignores; `status.json` keeps the plain strings of section 5.1. There are no page-level checkpoints in v1: a stopped unit keeps the records fetched so far and is fetched again in full next time.
- **Idempotent.** Records are merged by key, so re-fetching never duplicates; stored records that are not fetched again are kept.
- **Incremental: deferred.** Every run fetches the whole window again.
- **Budgeted.** `collect --max-requests N` stops cleanly at N `gh` calls. Every query asks for `rateLimit { remaining resetAt }`; at the primary limit the run stops with "resume after HH:MM". Secondary limits and transient errors (5xx, network) retry with backoff, then the unit is `partial`. Units not reached are left untouched.
- **Filters.** `collect [--repo X] [--metric Y] [--since D] [--until D] [--dry-run] [--no-avatars]`.
- **Avatars.** After the units, each distinct linked login (aliases applied; bots by their app name) is fetched once from `https://github.com/<login>.png` (redirects only to the GitHub avatar CDN; image content type and under 1 MB required) into `data/avatars/` with the aggregator's file names. Failures keep the placeholder and are listed in `data/raw/avatars-failed.json`.

### CLI
- `collect`: fetch raw data and avatars (exit 1 when a unit failed)
- `aggregate`: build `data/derived/` (including the contributor registry)
- `status`: per repo and metric, shows complete, partial, never-run or failed with record counts, the last collection time and failure reasons; no network
- `derive-repos`: write `data/derived/repos.json` from `data/config.yml` (interim, see section 7.6)

## 9. Metadata (`data/derived/meta.json`)

Read by a front-end to show freshness and gaps.

- Last sync time per repo and metric
- Coverage window per repo and metric
- Status per repo and metric: complete, partial, never-run, failed, with reason and error count
- Enrichment coverage (enriched records over total)
- Skipped statistics (disabled metric) and partial statistics (incomplete enrichment)
- Skipped corrupt JSONL lines, failed avatar downloads (for now listed in `data/raw/avatars-failed.json`, not yet in `meta.json`)
- Config window and the generation time

## 10. Error handling

- **Isolation.** Failures are isolated per repo and metric. A 404 or 403 on one repo is recorded as `failed` with the reason, and the rest continues.
- **Retries.** Transient errors (5xx, secondary rate limits) retry with backoff. After the retry limit, that unit is marked `partial`.
- **Storage.** Corrupt or half-written JSONL lines are skipped on read and reported in the metadata. Writes are append-only, so repeated keys are expected and the last record wins (section 5.1).
- **Contributors.** A missing login falls back to the unlinked identity. A failed avatar download falls back to the placeholder.

## 11. Testing

- Unit tests: config loader, checkpoint logic, bot filtering, aliases, contributor identity (linked, unlinked, alias merge).
- Metric plugins are tested against recorded `gh api` JSON fixtures with the `github.py` wrapper mocked. No network access.
- Aggregators are tested as pure functions on small hand-built record sets: empty windows, partial enrichment, disabled metrics.
- Curiosity tests: ties, missing enrichment, comment-thread reconstruction.
- Contributor tests: counts by kind, email never present in `derived/`, avatar failure fallback.
- End-to-end test: `aggregate` on `data-sample/` compared with a snapshot, which also keeps the sample valid.
- CI check: fails if `data/` or any file containing real repo names is tracked.

## 12. Scenes and scripts

The wrap is built from **scenes** linked together by **scripts**. This layer defines *what* is shown and in what order. How it is played and animated is in section 13.

### Scene
A reusable unit in its own file, with an `id`, a `type` and `params`.
- **Data scenes** bind to a derived dataset (a statistic, a curiosity, the contributor registry). A data scene declares `requires`: the datasets and fields it needs, and whether partial (not fully enriched) data is acceptable.
- **Static scenes** need no data: a message, an image, a short video, a title card.
- Scene types are folders in `web/scene-types/` (section 13). A type declares its params schema and its `requires`, so new types need no change to the core.
- A scene file may set an optional `title`, which the player shows on the progress line (the default is the `id`).

### Script
An ordered list of scene references, in its own file.
- `id`, `title`, `period` (for example the year 2026) and a default scope (all repos, or a group)
- each entry is a scene `id` with optional overrides (scope, period, params)
- each entry sets `on_missing_data`: `skip` or `fail`
- The Year Wrapped is one script. Any number of scripts can exist, and one scene can be used by several.

### Validation
`validate-script <script>` resolves every scene and reports:
- the datasets and fields the script needs, as a list that feeds back into this spec
- per scene: **supported**, **partial**, or **unsupported** by the data

It runs against `data-sample/` before any real collection, and later against the real `data/derived/meta.json`, where it also shows which scenes would be skipped.

### Sharing scenes and scripts
Scenes and generic scripts are meant to be shared. They live in the public repo (`scenes/`, `scripts/`). Anyone can use a scene as long as they can produce the datasets it requires, with our collector or with their own.

- **Loading.** The loader reads `scenes/` and `scripts/`, then `data/scenes/` and `data/scripts/`. A private file with the same `id` overrides the shared one. Private-only scenes and scripts are allowed.
- **Scope-agnostic scenes.** A shared scene never names a repo or group. The script, or a private override, supplies the scope, so group names stay private.
- **Dataset catalog.** `docs/datasets.md` lists every dataset name and its fields, for example `contributors.total` or `curiosities.biggest_pr_by_lines.value`. It is the contract between data and scenes. A scene may only require what the catalog lists, and `validate-script` enforces this. A scene that needs new data must extend the catalog in the same change.
- **Missing data.** `validate-script` names the datasets and fields that are missing and the metric that would produce them.
- **Media.** Small, licence-clean assets can live next to a shared scene. Large or private media is referenced from `data/assets/` or by URL.

### Layout
```
web/scene-types/             # scene types (section 13)
scenes/, scripts/            # shared definitions (public)
data/scenes/, data/scripts/  # private definitions (git-ignored)
data-sample/                 # dummy data used to validate the shared scenes
```

## 13. Presentation: playing a script

A script is played in a self-contained HTML page. The page has a Play button. Playing runs the scenes in order, it can be paused, a progress line lets the viewer jump to a scene, background music plays and can be muted, and scenes are animated.

### Animation engine
GSAP, vendored in `web/vendor/` together with its licence text and copied into each built page, so pages work offline. The maintainer confirms the current GSAP licence terms before the first public release.

### Timeline model
- Each scene produces one GSAP **timeline**: it can start, pause, resume and seek.
- The player controller holds the ordered scene list and each scene's duration. It builds a scene's timeline when the scene is entered and discards it when the scene is left. Durations are known up front, so the overall progress is the sum of the earlier scenes plus the current timeline's progress.
- **Duration.** A scene type declares a default duration in `type.yml`. A script entry can override it. A video scene declares its duration in its scene file.
- **Transitions.** The controller plays a transition preset between scenes. A script sets a default transition and an entry can override it. Scenes do not animate their own entry and exit.

### Scene types
One folder per type in `web/scene-types/<type>/`:
- `type.yml`: params schema, default duration, default `requires`. Used by `validate-script` and `build`. In the first version the params schema is the list `required_params`; `validate-script` checks that each is present. Params named `items`, `supporting` and `steps` carry `{label, value}` pairs (a `steps` entry may also carry a `lead` text shown before the number on the same line, or be just `{text}`) whose `value` is a data reference, and a top-level `value` param is a data reference only for types that list it in `required_params`; `validate-script` checks that each reference resolves to a number. Params named `names` and `records` are data references that must resolve to a list.
- `render.js`: `export default { render(ctx) }`, where `ctx` is `{container, data, params, duration, partial, scope, period, gsap, presets}`. It returns a GSAP timeline of about `duration` seconds. It touches only `container`, and it receives the data for the scene's `requires` in the shape of the derived files (section 7.6). `partial` lists the datasets computed from incomplete data, so a renderer may label them. The build rewrites the single `export default` into a registry assignment and rejects `import` lines, because pages open from disk and browsers block module imports on `file://`.

Initial types: `message`, `stats` (a grid of counting numbers with an optional heading), `bignumber` (one hero number with an optional heading above it, optional supporting figures and an optional count-up duration, ease and tail beats, and an optional odometer-style counter), `sequence` (a heading and a list of steps, each a number with a label and an optional lead text on the same line, or a plain text, appearing one by one), `repogrid` (a heading with a highlighted count, a grid of folders and an optional footnote), `headcount`, `curiosity` (a teaser, the first record's number, a unit and a context line filled from the record, with optional singular forms), and a media type for images and short video.

### Animation presets
`web/presets/` holds shared building blocks for renderers and transitions: fade, slide, scale-in, count-up numbers, staggered lists, pop-in avatars, bubble-in and swell-in (appear, grow past the final size, settle back). New presets are added here, and any renderer can use them.

### Controls
- **Start screen** with a Play button. The click is also what lets the browser start audio.
- **Control bar:** play/pause, a progress line, a mute button.
- **Progress line.** It has one segment per scene, sized by duration, with the scene title on hover. Clicking a segment jumps to the start of that scene. The current scene is highlighted. Dragging within the current scene scrubs the timeline.
- **Jumping.** The controller discards the current timeline, builds the target scene at its start and keeps the playing or paused state.
- **Keyboard.** Space toggles play and pause, left and right arrows move between scenes, and `M` toggles mute.
- **End.** After the last scene the page shows a replay option.

### Music
- A script names one track: `music: {file, volume, loop}`, with the file in `data/assets/` or a URL. It fades in on Play and loops.
- The mute button toggles it, and the choice is remembered in the browser.
- Music pauses and resumes with the script, and is not interrupted by jumping between scenes.
- Music files are never committed to the public repo (licensing). They are referenced from `data/assets/`.

### Build
`team-wrapped build <script> [--data data|data-sample]`:
1. Runs script validation. Scenes that are unsupported and set `on_missing_data: fail` stop the build. Those set to `skip` are left out and listed in the output.
2. Resolves each scene's data slice for the script's scope and period.
3. Writes `dist/<script-id>/index.html`: the player, the scene list and only the data each scene needs, embedded as JSON, so the page opens from disk without a server.
4. Copies avatars and media next to it in `dist/<script-id>/assets/`.

A page built from `data/` contains real data and is private. A page built with `--data data-sample` can be shared as a demo.

### Testing
- `build` runs on `data-sample` in CI and must succeed for every shared script.
- A headless-browser smoke test loads the built page, clicks Play, pauses, jumps to the last scene through the progress line and toggles mute, and fails on any console error.
- Renderers are tested by building a timeline on sample data and checking that its duration matches the scene's duration.

## 14. Themes

A theme controls the look of a built page: colours, a font, a logo on the start and end screens, and background images that change per scene. The repo ships only the neutral `default` theme (the built-in look); a team's brand lives in a private theme folder so that no company branding or trademarks are committed.

- **Folder.** `themes/<name>/theme.yml` plus asset files, found in the repo root, in `data/`, or in the chosen data folder; later locations override earlier ones. Brand themes go in `data/themes/<name>/` (git-ignored). Theme names match `[A-Za-z0-9][A-Za-z0-9_-]*`.
- **`theme.yml`.** `colors` (any of: `background`, `text`, `accent`, `warning`, `surface`, `controls-bg`, `button-bg`, `button-text`, `focus`, `folder-top`, `folder-bottom`, `folder-tab`, `folder-text`), `font`, `logo` (a relative path), `backdrop` (`images`: relative paths, cycled by scene index; `opacity`: 0 to 1). Unknown keys are errors.
- **Safety.** Colour values must be `#hex` or `rgb()`/`rgba()`, the font a comma-separated list of up to 10 families, each a quoted name or a plain name, and asset paths relative and inside the theme folder; assets in one theme must not share a file name. Anything else is a load error. Nothing from a theme is inserted into the page unvalidated.
- **Choosing.** `build --theme NAME`, else the script's `theme:` key, else `default`.
- **Output.** Non-default colours and font become CSS variable overrides in the page; assets are copied to `assets/theme/`; the logo is shown above the title on the start screen and above Replay on the end screen; the backdrop images appear behind the scenes with a short cross-fade. With no theme the page is unchanged.

## 15. Out of scope (for now)

- Visual design details (colours, typography, layouts), which come with the first renderers
- Delivery speed (time to merge, time to first review), contributor footprint statistics and repo comparison tables. They can be added later as aggregate modules because the raw data already supports them
- Issues, releases and CI workflow metrics (the plugin interface allows them later)
- Per-person leaderboards
- A helper that generates groups from org-config. This would be an optional private script outside the generic core
