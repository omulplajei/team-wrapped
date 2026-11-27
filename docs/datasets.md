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
| `list[].login` | GitHub login; absent for `unlinked` contributors |
| `list[].avatar_file` | local avatar path (placeholder for unlinked) |
| `list[].kind` | `human`, `bot` or `unlinked` |
| `list[].first_activity`, `last_activity` | dates |

## repos
Metric: any. Not time-bucketed. A repository is "touched" when it has at least one commit (author date), pull request (created or merged date), review (submitted date) or comment (created date) inside the window, from any author including bots, among the enabled metrics. `total` equals the length of `list`, which is ordered alphabetically by `name`. The dataset is partial when any in-scope repository's status for an enabled metric is not complete. An empty list counts as missing data for scenes that require `list.name`, so scripts mark such scenes `on_missing_data: skip`.

| Dataset | Fields |
|---|---|
| `repos.touched` | `total`; `list[].name` |

## delivery_volume
| Dataset | Fields | Metric | Enriched |
|---|---|---|---|
| `delivery_volume.commits` | `count`, `merge_count`, `non_merge_count` per bucket | commits | no |
| `delivery_volume.lines` | `additions`, `deletions`, `net`, `files_changed` per bucket; `total_additions`, `total_deletions`, `total_net` for the window | commits | yes |
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
Each dataset is a **list** of up to N records, best first (`value`, plus the fields named below). Not time-bucketed, but limited to the scope and window. Scenes show the first record. Records never carry people or PR titles.

| Dataset | Record fields | Metric | Enriched |
|---|---|---|---|
| `curiosities.longest_comment_chain` | `value` (comments in the longest code-review thread), `repo`, `pr_number` | comments | no |
| `curiosities.most_commented_pr` | `value` (comments on one PR, both kinds), `repo`, `pr_number` | comments | no |
| `curiosities.most_commits_pr` | `value` (commits in one PR), `repo`, `pr_number` | pull_requests | yes |
| `curiosities.most_files_pr` | `value` (files changed in one PR), `repo`, `pr_number` | pull_requests | yes |
| `curiosities.biggest_pr_by_lines` | `value` (additions + deletions), `repo`, `pr_number` | pull_requests | yes |
| `curiosities.most_lines_deleted_pr` | `value` (lines deleted in one PR), `repo`, `pr_number` | pull_requests | yes |
| `curiosities.most_reviewed_pr` | `value` (reviews on one PR), `repo`, `pr_number` | reviews | no |
| `curiosities.longest_lived_pr` | `value` (days from created to merged or closed), `repo`, `pr_number` | pull_requests | no |
| `curiosities.most_review_rounds_pr` | `value` (rounds on one PR), `repo`, `pr_number` | reviews | yes |
| `curiosities.biggest_commit` | `value` (lines in one commit), `repo`, `sha`, `files` | commits | yes |
| `curiosities.busiest_day` | `value` (commits that day), `date` (YYYY-MM-DD), `merged_prs` | commits, pull_requests | no |
| `curiosities.busiest_month` | `value` (commits that month), `month` (YYYY-MM), `merged_prs` | commits, pull_requests | no |
| `curiosities.longest_commit_streak` | `value` (consecutive days with a commit), `from`, `to` (YYYY-MM-DD) | commits | no |
| `curiosities.longest_merge_streak` | `value` (consecutive days with a merged PR), `from`, `to` (YYYY-MM-DD) | pull_requests | no |

## meta
Always available. See spec section 9.

| Field | Meaning |
|---|---|
| `status` | per repo and metric: complete, partial, never-run, failed |
| `coverage` | window covered per repo and metric |
| `enrichment_coverage` | enriched records over total |
| `partial_datasets` | datasets computed from incomplete data |
