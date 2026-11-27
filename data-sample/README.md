# data-sample

Dummy data only: a sample `config.yml`, raw records and derived output, in the same layout as the private `data/` folder. It is used to try the tool and to validate the shared scenes in `../scenes/`.

## Contents so far
- `derived/`: `summary.json`, `delivery_volume.json`, `contributors.json`, `repos.json`, `curiosities.json`, `meta.json`. Each file holds `period` and `scopes` (`all`, `group:<name>`). All values are made up. `repos.json` is produced by `derive-repos` from `config.yml`.
- `avatars/`: solid-colour placeholder images, one per contributor, plus `placeholder.png` for unlinked contributors.
- `meta.json` marks `delivery_volume.lines` as partial (enrichment coverage below 100%), so scenes that allow partial data can be tested.

Raw records will be added when the collector is built.
