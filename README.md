# team-wrapped

Collect GitHub activity for a set of repositories and play it back as a "wrapped" page: scenes linked by a script, with animation and background music.

Status: the scene, validation and player layers work on the sample data. `collect` fetches GitHub activity into raw records and `aggregate` builds the derived data from them; see `docs/superpowers/`.

## Try it on the sample data

```bash
pip install pyyaml pytest
PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample
./build.sh year-wrapped --data data-sample
```
Then open `dist/year-wrapped/index.html` in a browser. If your browser or tool blocks local files from loading their scripts, serve the folder instead:

```bash
python3 -m http.server 8000 --directory dist/year-wrapped
```

## Building a page

The player is one static HTML page. It does not read your data or theme while it plays, so it has to be **built** from them: `build` checks the script against the data, embeds only the data each scene needs, copies the theme's assets and writes `dist/<script>/index.html`. Rebuild after changing data, scenes, scripts or a theme.

`build.sh` is a short wrapper around the build command that works from any folder:

```bash
./build.sh [SCRIPT_ID] [OPTIONS]
```

| Part | Meaning | Default |
|---|---|---|
| `SCRIPT_ID` | Script to build, from `scripts/` or `data/scripts/` | `year-wrapped` |
| `--data FOLDER` | Data folder under the repo root (`data` for your private data, `data-sample` for the demo data) | `data` |
| `--theme NAME` | Theme to apply (see Themes below) | the script's `theme:`, else the built-in look |
| `--out FOLDER` | Output folder under the repo root | `dist` |

Examples:

```bash
./build.sh                                          # year-wrapped from data/ with the built-in look
./build.sh year-wrapped --data data-sample          # demo data
./build.sh year-wrapped --data data --theme my-brand
```

It prints the page path when it is done, and stops with a message (exit code 1 or 2) if a scene cannot be supported by the data or a theme is invalid; nothing is written in that case. A page built from `data/` contains real data: do not publish `dist/` (it is git-ignored). The script needs Python 3.11+ and PyYAML (`pip install pyyaml`); without `build.sh` the same thing is `PYTHONPATH=src python3 -m team_wrapped build ...`.

## Layout

- `scenes/`, `scripts/`: shared scene and script definitions.
- `web/`: the player, scene types (one folder each, e.g. `cast` for the closing people scene, `capability-flow` for the "The whole year in a postcard" honeycomb), animation presets and vendored GSAP.
- `docs/datasets.md`: the catalog of datasets a scene may require.
- `data-sample/`: dummy data in the same layout as your private `data/` folder.
- `data/` and `dist/`: private, git-ignored. Put your own derived data, scenes, scripts and music in `data/`.

## Music

A script can set `music: {file: theme.mp3, volume: 0.3}`. The file is read from `data/assets/` (or give an `https://` URL). Music files are never committed.

## Repositories config

Your private `data/config.yml` lists the GitHub organisation, the repositories and optional groups (see `data-sample/config.yml`). `derive-repos` turns it into the dataset the repositories scene needs:

```bash
PYTHONPATH=src python3 -m team_wrapped derive-repos --data data
```

For now every configured repository counts as "touched"; the file is marked `"basis": "configuration"` until activity is collected from GitHub.

## Collecting from GitHub

`collect` reads `data/config.yml` and writes the raw records `aggregate` needs. It talks to GitHub only through the [`gh` CLI](https://cli.github.com/) and only through the GraphQL API (`gh api graphql`), so log in once and the tool never handles a token:

```bash
gh auth login
PYTHONPATH=src python3 -m team_wrapped collect --data data --dry-run      # the plan: repos, metrics, window; no API calls
PYTHONPATH=src python3 -m team_wrapped collect --data data
PYTHONPATH=src python3 -m team_wrapped status --data data                # what is complete, partial, failed or never run
PYTHONPATH=src python3 -m team_wrapped aggregate --data data
```

| Option | Meaning |
|---|---|
| `--repo NAME` | only this repository (repeatable; must be in the config) |
| `--metric NAME` | only this metric (repeatable; must be enabled in the config). `pull_requests`, `reviews` and `comments` come from one search |
| `--since YYYY-MM-DD`, `--until YYYY-MM-DD` | the window for this run only (default: the config's). Dates are inclusive and read in the config `timezone` |
| `--max-requests N` | stop cleanly after N `gh` calls |
| `--no-avatars` | skip avatar downloads (or set `avatars: {download: false}`) |
| `--dry-run` | print the plan and make no API calls: the window, then per repository and metric `full` or `incremental from <date>` |
| `--full` | ignore the checkpoints and fetch the whole window (new checkpoints are written when it completes) |
| `--overlap-days N` | how many days before the last covered commit time an incremental run fetches again (default 7, 0 or more) |

What it writes, per repository: `data/raw/<repo>/commits.jsonl`, `pull_requests.jsonl`, `reviews.jsonl`, `comments.jsonl` (section 5.1 of the spec), `status.json` (`complete`, `partial` or `failed` per metric), `status-detail.json` (reason, collection time, record count, full or incremental) and `checkpoint.json` (what each metric has collected, for incremental runs; the aggregator ignores it). Commits come from the default branch; commit and PR sizes come with the same queries, so there is no separate enrichment pass. Avatars go to `data/avatars/` (from `https://github.com/<login>.png`); logins whose download failed use the placeholder and are listed in `data/raw/avatars-failed.json`. Raw commit records keep author names and emails: they stay in the git-ignored `data/` and never reach `derived/`.

Each repository and metric is written as soon as it finishes. A missing or inaccessible repository is marked `failed` and the run continues; the exit code is 1 when anything failed. Transient errors (5xx, network, secondary rate limits) are retried with backoff. When the hourly rate limit or `--max-requests` is reached, the run stops cleanly: the unit in progress is `partial` with what was fetched, later units are left as they were, and the message says when to resume ("resume after HH:MM").

Re-running is safe: records are merged by key, so nothing is duplicated, a record fetched again (a pull request that has since been merged or reviewed) replaces the stored one, and records not fetched again are kept.

### Incremental runs

The first run fetches the whole window. Every repository and metric that ends `complete` then records a checkpoint (`data/raw/<repo>/checkpoint.json`: when it synced, the window it collected, and how far the data is complete, never past the start of that run), and the next run of the same command fetches only the delta:

```bash
PYTHONPATH=src python3 -m team_wrapped collect --data data        # today: 2026-01-01 .. now, in full
# two weeks later, the same command:
PYTHONPATH=src python3 -m team_wrapped collect --data data        # only what changed since; progress says "since <date>"
```

- **Commits** are fetched from the last covered time minus `--overlap-days` (7 by default: a late push or a rebase keeps the old commit date) to the window end. Moving `since` earlier also fetches the missing start; a window that does not touch what was collected is fetched in full.
- **Pull requests, reviews and comments** come from one search, so re-fetching a pull request refreshes its reviews and comments. A run fetches those updated since the last sync minus a day (any activity, including on open pull requests, bumps the update time) plus those created after the previous window end when `until` moved later. Moving `since` earlier than the checkpoint's fetches the whole window again (with a notice).
- A `partial`, `failed` or stopped unit keeps its previous checkpoint, so the next run fetches that delta again. A checkpoint that cannot be read is reported and ignored (that metric is fetched in full).
- `status` shows each metric's last sync and covered range.

Incremental runs do not notice what disappeared: deleted or force-pushed-away commits and deleted pull requests stay in the raw files. Run with `--full` now and then to re-fetch every record of the window. Because records are merged by key, even `--full` keeps records of deleted items: delete `data/raw/<repo>/` before it for a clean copy.

## Aggregating raw data

`aggregate` reads `data/config.yml` and the raw JSON-lines files in `data/raw/<repo>/` (`commits.jsonl`, `pull_requests.jsonl`, `reviews.jsonl`, `comments.jsonl`, `status.json`; the exact fields are in section 5.1 of the spec) and writes `data/derived/`: `summary`, `delivery_volume`, `curiosities`, `contributors`, `repos` and `meta.json`, for the scopes `all` and `group:<name>`. It never writes to `raw/`, and running it twice gives the same files (apart from `generated_at`).

```bash
PYTHONPATH=src python3 -m team_wrapped aggregate --data data
```

Datasets computed from incomplete data (a repository that is not `complete`, or commits and PRs not yet enriched) are listed in `meta.json` under `partial_datasets`. `collect` writes the raw files (see above); `data-sample/` has derived files only and no raw records yet.

## Themes

`build` takes `--theme NAME` (or a `theme:` line in a script). A theme is a folder `themes/<name>/` with a `theme.yml` (colours, font, logo, backdrop images) and its asset files; put your own in `data/themes/<name>/`, which is git-ignored, so brand assets stay out of the repo. See section 14 of the spec for the format.

The capability colours of the "The whole year in a postcard" scene are theme colours too: `cat-core`, `cat-extension`, `cat-support` and `cat-none` (CSS variables `--tw-cat-core` and so on; defaults soft green, blue, purple and grey). Each hexagon is filled with its colour at low opacity and outlined in it; its blocks use it at full strength.

## The whole year in a postcard

The `capability-commits` scene (type `capability-flow`, in `year-wrapped` with `scope: all`) reads `commit_flow`: one hexagon per configured group, labelled with its `label` and coloured by its `category`, and every commit of the window falls into it as a block on the day it was authored, so the piles grow through the year while a month bar runs along the bottom. A block's side is `k * sqrt(lines)`, kept between a minimum (0-line commits, drawn at least 1.5 px) and a third of the hexagon width, so its area grows with the lines changed. One `k` is shared by all hexagons, chosen so that the busiest group's blocks cover half of its hexagon: busy capabilities fill up and quiet ones stay low, so hexagons compare honestly. The largest commits (top 0.5%, at least three) flash as they land. The hexagons are arranged automatically (core in the middle); the scene file shows an optional `layout` param to place them by hand.

## Tests

```bash
python3 -m pytest
node --test tests-js/
```

The design is in `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`.
