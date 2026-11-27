# team-wrapped

Collect GitHub activity for a set of repositories and play it back as a "wrapped" page: scenes linked by a script, with animation and background music.

Status: the scene, validation and player layers work on the sample data. The collector and aggregator are not built yet; see `docs/superpowers/`.

## Try it on the sample data

```bash
pip install pyyaml pytest
PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample
PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample
```
Then open `dist/year-wrapped/index.html` in a browser. If your browser or tool blocks local files from loading their scripts, serve the folder instead:

```bash
python3 -m http.server 8000 --directory dist/year-wrapped
```

## Layout

- `scenes/`, `scripts/`: shared scene and script definitions.
- `web/`: the player, scene types, animation presets and vendored GSAP.
- `docs/datasets.md`: the catalog of datasets a scene may require.
- `data-sample/`: dummy data in the same layout as your private `data/` folder.
- `data/` and `dist/`: private, git-ignored. Put your own derived data, scenes, scripts and music in `data/`.

## Music

A script can set `music: {file: theme.mp3, volume: 0.3}`. The file is read from `data/assets/` (or give an `https://` URL). Music files are never committed.

## Themes

`build` takes `--theme NAME` (or a `theme:` line in a script). A theme is a folder `themes/<name>/` with a `theme.yml` (colours, font, logo, backdrop images) and its asset files; put your own in `data/themes/<name>/`, which is git-ignored, so brand assets stay out of the repo. See section 14 of the spec for the format.

## Tests

```bash
python3 -m pytest
node --test tests-js/
```

The design is in `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`.
