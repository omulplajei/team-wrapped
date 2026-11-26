# Dataset catalog

The contract between data and scenes. A scene may only require datasets and fields listed here. If a scene needs something new, add it here in the same change.

Every dataset can be sliced by scope (`all`, a group, or a repo) and time bucket unless noted. The metric column says which metric must be enabled to produce it. Datasets marked *enriched* are partial until the enrichment pass completes.

Source of truth for definitions: `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 7.

## contributors
Metric: any. Not time-bucketed.

| Field | Meaning |
|---|---|
| `total` | all contributors |
| `by_kind` | counts of `human`, `bot`, `unlinked` |
| `list[].avatar_file` | local avatar path (placeholder for unlinked) |
| `list[].kind` | `human`, `bot` or `unlinked` |
| `list[].first_activity`, `last_activity` | dates |

## delivery_volume
| Dataset | Fields | Metric | Enriched |
|---|---|---|---|
| `delivery_volume.commits` | `count`, `merge_count`, `non_merge_count` per bucket | commits | no |
| `delivery_volume.lines` | `additions`, `deletions`, `net`, `files_changed` per bucket | commits | yes |
| `delivery_volume.prs` | `opened`, `merged` per bucket | pull_requests | no |
| `delivery_volume.pr_size` | distribution of `lines_changed`, `files_changed`, `commit_count` for merged PRs | pull_requests | yes |

## review_collab
| Dataset | Fields | Metric |
|---|---|---|
| `review_collab.reviews` | `count` per bucket | reviews |
| `review_collab.review_comments` | `count` per bucket | comments |
| `review_collab.outcome_mix` | `approved`, `changes_requested`, `commented` | reviews |
| `review_collab.comments_per_pr` | distribution | comments |
| `review_collab.review_rounds_per_pr` | distribution | reviews |
| `review_collab.review_load` | distribution of reviews per reviewer (aggregate, no names) | reviews |
| `review_collab.reviewer_pairs` | optional, off by default | reviews |

## summary
| Dataset | Fields |
|---|---|
| `summary.totals` | commits, merged PRs, reviews, comments for the window |
| `summary.period_change` | change against the previous period, per statistic |
| `summary.busiest_quietest` | busiest and quietest bucket per statistic |
| `summary.activity_by_weekday`, `summary.activity_by_hour` | counts in the configured timezone |

## curiosities
Each holds the top N records: `value`, `repo`, and a `pr_number` or `sha`. Not time-bucketed, but limited to the scope and window.

| Dataset | Value | Metric | Enriched |
|---|---|---|---|
| `curiosities.longest_comment_chain` | comments in the longest code-review thread | comments | no |
| `curiosities.most_commented_pr` | comments on one PR, both kinds | comments | no |
| `curiosities.most_commits_pr` | commits in one PR | pull_requests | yes |
| `curiosities.most_files_pr` | files changed in one PR | pull_requests | yes |
| `curiosities.biggest_pr_by_lines` | additions + deletions | pull_requests | yes |
| `curiosities.most_reviewed_pr` | reviews on one PR | reviews | no |
| `curiosities.longest_lived_pr` | days from created to merged or closed | pull_requests | no |
| `curiosities.most_review_rounds_pr` | rounds on one PR | reviews | yes |
| `curiosities.biggest_commit` | lines and files in one commit | commits | yes |
| `curiosities.busiest_day` | commits and merged PRs on one day | commits, pull_requests | no |

## meta
Always available. See spec section 9.

| Field | Meaning |
|---|---|
| `status` | per repo and metric: complete, partial, never-run, failed |
| `coverage` | window covered per repo and metric |
| `enrichment_coverage` | enriched records over total |
| `partial_datasets` | datasets computed from incomplete data |
