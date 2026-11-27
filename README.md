# team-wrapped

Collect GitHub activity for a set of repositories and play it back as a "wrapped" page: scenes linked by a script, with animation and background music.

Status: the scene, validation and player layers work on the sample data. The aggregator builds the derived data from raw records; the collector that writes those records is not built yet; see `docs/superpowers/`.

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
- `web/`: the player, scene types (one folder each, e.g. `cast` for the closing people scene), animation presets and vendored GSAP.
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

## Aggregating raw data

`aggregate` reads `data/config.yml` and the raw JSON-lines files in `data/raw/<repo>/` (`commits.jsonl`, `pull_requests.jsonl`, `reviews.jsonl`, `comments.jsonl`, `status.json`; the exact fields are in section 5.1 of the spec) and writes `data/derived/`: `summary`, `delivery_volume`, `curiosities`, `contributors`, `repos` and `meta.json`, for the scopes `all` and `group:<name>`. It never writes to `raw/`, and running it twice gives the same files (apart from `generated_at`).

```bash
PYTHONPATH=src python3 -m team_wrapped aggregate --data data
```

Datasets computed from incomplete data (a repository that is not `complete`, or commits and PRs not yet enriched) are listed in `meta.json` under `partial_datasets`. The collector (`collect`, not built yet) will write the raw files, so for now you provide them yourself; `data-sample/` has derived files only and no raw records yet.

## Themes

`build` takes `--theme NAME` (or a `theme:` line in a script). A theme is a folder `themes/<name>/` with a `theme.yml` (colours, font, logo, backdrop images) and its asset files; put your own in `data/themes/<name>/`, which is git-ignored, so brand assets stay out of the repo. See section 14 of the spec for the format.

## Tests

```bash
python3 -m pytest
node --test tests-js/
```

The design is in `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`.
