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
| `list[].id` | sequential id (`c001`, ...) assigned after sorting; not derived from any email or name |
| `list[].login` | GitHub login; absent for `unlinked` contributors and for bots matched by author name |
| `list[].name` | bots only: display name, the `bot_names` entry for the login, else the login without the trailing `[bot]` (`sample-bot[bot]` is `sample-bot`); for a bot without a login (an unlinked author whose name matched `bot_patterns`, such as `Deployment Script`), that service name. Humans and `unlinked` contributors never have one |
| `list[].avatar_file` | local avatar path (placeholder for unlinked) |
| `list[].kind` | `human`, `bot` or `unlinked` |
| `list[].first_activity`, `last_activity` | dates |

Contributors are identified by login (aliases applied), then email, then name; the three kinds never merge by accident, and an email alias applies only to a record without a login. Commit co-authors (`Co-authored-by:` trailers, for example AI coding tools) count as contributors exactly like commit authors, so a person who only co-authors is a contributor too; co-authors do not change any other dataset. The dataset is partial when any in-scope repository's status for an enabled metric is not complete.

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

`lines` totals sum the enriched non-merge commits authored inside the window; merge commits are skipped because they repeat the lines of the commits they merge. Enriched means the record has `enriched: true` (the boolean) and whole-number `additions` and `deletions`. The dataset is omitted when no non-merge commit in scope is enriched, and partial when any in-window non-merge commit in scope is not.

## commit_flow
Metric: commits. Scope `all` only (there are no `group:` or `repo:` scopes: the dataset already holds one record per group). Not time-bucketed. One year of commits as blocks, per capability (a configured group of repos).

| Dataset | Fields |
|---|---|
| `commit_flow.groups` | a **list**, one record per configured group in config order: `name`, `label`, `category` (`core`, `extension` or `support`; absent when `group_info` sets none), `total` (commit count), `commits` (list of `[day, lines]` pairs) |
| `commit_flow.window` | `days` (length of the window in days), `start` (YYYY-MM-DD) |

`day` is the number of whole local calendar days (configured timezone) from the window `start`, 0-based, so the last day is `days - 1`. `lines` is additions + deletions of the commit, or 0 when the commit is not enriched. Only non-merge commits of the group's repositories count, by author date and inside the window; a repository in several groups counts in each. `commits` is ordered by day, then authored timestamp, then sha. A group without qualifying commits is still listed with `total` 0 and empty `commits`. `label` is the group name unless `group_info` sets one. The dataset needs `since` and `until` in the config (or `aggregate --since/--until`) and at least one group; otherwise it is omitted. It is partial when any in-window non-merge commit of a grouped repository is not enriched, or the commits status of any grouped repository is not complete. Privacy: no author, message or hash is written, only the day and the size. A scene reads it with scope `all`.

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

`summary.totals` counts every commit by author date (merge commits and bots included), every PR by merge date, every review by submitted date except reviews written by the PR's own author (aliases resolved), and every comment of either kind by created date. Totals of disabled metrics are not written.

## curiosities
Each dataset is a **list** of up to N records, best first (`value`, plus the fields named below). Not time-bucketed, but limited to the scope and window. Scenes show the first record. Records never carry people or PR titles. A dataset is empty (or absent) when there is nothing to report: records with a `value` of 0 or null fields are never written. Every record carries all the fields of its row. Dates and months are calendar dates in the configured time zone.

Windowing: comment and review curiosities count the comments and reviews whose own timestamp is inside the window (reviews by the PR's own author do not count); PR curiosities use the PRs created or merged inside the window; commit, day, month and streak curiosities use the local date of the commit author date or PR merge date. Ties go to the earlier date, then the repo name, then the PR number. Streaks and busiest days list distinct runs and days, so the list can hold several records. `biggest_commit` skips merge commits. Bots without a login are counted as `unlinked` contributors, and bot commits count towards commit streaks and busiest day. `longest_lived_pr` skips open PRs and counts whole days. `most_review_rounds_pr` counts `changes_requested` reviews, so it is computed from reviews and is not affected by PR enrichment.

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
| `curiosities.most_review_rounds_pr` | `value` (rounds on one PR: its `changes_requested` reviews), `repo`, `pr_number` | reviews | no |
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
| `enrichment_coverage` | enriched records (`enriched: true`) over total, rounded down to 2 decimals |
| `partial_datasets` | datasets computed from incomplete data |
