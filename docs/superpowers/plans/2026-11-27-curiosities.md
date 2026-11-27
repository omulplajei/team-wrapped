# Curiosity Scenes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `curiosity` scene type and seven curiosity scenes (busiest month, busiest day, longest streak, longest conversation, most reviewed PR, the PR that kept going, spring cleaning) to the Year Wrapped, between the recap and the extent scenes. Two more (merged-PR streak, most commented PR) exist as ready scene files that are not in the script.

**Architecture:** Curiosity datasets are ranked lists of records in `curiosities.json` (spec 7.6). The new scene type shows rank 1 of a list: a teaser line, a big number (swelling in, no count-up) in the accent colour, a unit label and a context line filled from the record's fields. A validator rule checks that a `records` param resolves to a list. Sample data makes every scene playable now; with real data each scene is skipped until the aggregator produces its dataset.

**Tech Stack:** Python 3.11+ (pytest), classic-script JavaScript presets and renderer tested with `node --test`, GSAP timelines.

Builds on the earlier plans (all on `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import`; `render(ctx)` returns a GSAP timeline and touches only `container`; textContent only.
- Curiosity datasets: dataset `curiosities.<name>` is a **list** of records at `scopes[<scope>][<name>]` in `curiosities.json`, sorted by `value` descending; the scene shows the first record. Record fields: `value` (number) plus, depending on the curiosity, `repo`, `pr_number`, `date` (YYYY-MM-DD), `month` (YYYY-MM), `from`, `to` (YYYY-MM-DD), `merged_prs`. Nothing about people or PR titles.
- A param named `names` or `records` is a data reference that must resolve to a list (`'<ref>' does not resolve to a list`); an empty list makes the scene unsupported through its `requires.fields` check.
- Template placeholders in `context`: `{key}` replaced from the record: `date` -> weekday day month ("Tuesday 14 March"), `from` and `to` -> day month ("3 March"), `month` -> month name ("March"), keys ending in `_number` -> plain digits (no thousands separator), other numbers -> `presets.format`, other values -> `String`, missing -> empty string. Dates are formatted in UTC with `en-GB`, so the time zone never shifts a day.
- Timing: teaser fades in at 0 (0.6 s); the number swells at 0.9 s (`presets.swellIn`); the unit (and the partial badge, if any) fade in at 1.35 s (0.4 s); the context fades in at 1.85 s (0.5 s); default scene duration 6 s.
- Numbers use the accent colour (`var(--tw-accent)`); no hard-coded hex colours in `player.css` outside `:root`.
- Shared scenes are scope-agnostic; sample data uses only made-up names (`sample-*`); nothing org-specific is committed.
- Run tests with `python3 -m pytest -q` and `node --test tests-js/`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
src/team_wrapped/scenes/validate.py           # modify: records must resolve to a list
tests/scenes/test_validate.py                 # modify
tests/scenes/test_catalog_and_types.py        # modify: new dataset names
docs/datasets.md                              # modify: curiosity records
data-sample/derived/curiosities.json          # create
web/presets/presets.js                        # modify: formatDate, formatMonth, fillTemplate
tests-js/presets.test.js                      # modify
web/scene-types/curiosity/type.yml, render.js # create
tests-js/curiosity.test.js                    # create
web/player/player.css                         # modify
scenes/curiosity-*.yml                        # create: 9 scenes
scripts/year-wrapped.yml                      # modify: 7 curiosity entries
tests/scenes/test_build.py, test_validate.py  # modify: year-wrapped expectations
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify
```

---

### Task 1: Data contract: validator rule, catalog and sample data

**Interfaces:**
- Consumes: `validate_script` in `src/team_wrapped/scenes/validate.py`; the `run`/`make_data`/`TYPES`/`CATALOG` helpers in `tests/scenes/test_validate.py`; `docs/datasets.md`.
- Produces: the `records` list rule; catalog rows for the new curiosities; `data-sample/derived/curiosities.json`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/curiosities
```
Expected: `Switched to a new branch 'feature/curiosities'`

- [ ] **Step 2: Write the failing tests**

In `tests/scenes/test_validate.py`: add to `TYPES`: `"curiosity": SceneType("curiosity", 6.0, ["teaser", "records", "unit"], Path(".")),`; add `"curiosities.busiest_day"` to `CATALOG`; in `make_data` write one more file after `repos.json`:
```python
    (d / "curiosities.json").write_text(json.dumps(
        {"scopes": {"all": {"busiest_day": [{"value": 87, "date": "2026-03-14", "merged_prs": 12}]}}}))
```
and append:
```python
CUR_REQ = [{"dataset": "curiosities.busiest_day", "fields": ["value", "date"]}]


def test_curiosity_records_must_resolve_to_a_list(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"teaser": "T", "records": "curiosities.busiest_day", "unit": "commits"}
    assert run(tmp_path / "a", CUR_REQ, params=ok, type_="curiosity").results[0].status == "supported"
    report = run(tmp_path / "b", CUR_REQ, params=dict(ok, records="curiosities.busiest_day.value"), type_="curiosity")
    assert "records 'curiosities.busiest_day.value' does not resolve to a list" in report.results[0].problems
    report = run(tmp_path / "c", CUR_REQ, params=dict(ok, records="curiosities.nope"), type_="curiosity")
    assert "records 'curiosities.nope' does not resolve to a list" in report.results[0].problems
```
In `tests/scenes/test_catalog_and_types.py`, in `test_catalog_lists_planned_datasets`, add these to the expected names: `"curiosities.busiest_day"`, `"curiosities.busiest_month"`, `"curiosities.longest_commit_streak"`, `"curiosities.longest_merge_streak"`, `"curiosities.most_lines_deleted_pr"`, `"curiosities.longest_comment_chain"`, `"curiosities.most_reviewed_pr"`, `"curiosities.most_commented_pr"`, `"curiosities.most_commits_pr"`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/scenes -q`
Expected: FAIL: the `records` rule is missing, and the catalog lacks the new names.

- [ ] **Step 4: Implement the validator rule**

In `src/team_wrapped/scenes/validate.py`, replace the existing `names` check
```python
        names_ref = scene.params.get("names")
        if isinstance(names_ref, str) and not isinstance(resolve_ref(datasets, names_ref), list):
            problems.append(f"names '{names_ref}' does not resolve to a list")
```
with:
```python
        for list_param in ("names", "records"):
            list_ref = scene.params.get(list_param)
            if isinstance(list_ref, str) and not isinstance(resolve_ref(datasets, list_ref), list):
                problems.append(f"{list_param} '{list_ref}' does not resolve to a list")
```

- [ ] **Step 5: Update the catalog**

Read the `## curiosities` section of `docs/datasets.md`. Replace its introduction sentence and table with:
```markdown
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
```
(Keep the rest of the file as it is. If the section's rows were in a different order, the above fully replaces them.)

- [ ] **Step 6: Create the sample data**

`data-sample/derived/curiosities.json` (scopes `all` and `group:alpha`, the same dataset keys in both):
```json
{
  "period": {"since": "2026-01-01", "until": "2026-12-31"},
  "scopes": {
    "all": {
      "longest_comment_chain": [
        {"value": 23, "repo": "sample-api", "pr_number": 482},
        {"value": 19, "repo": "sample-web", "pr_number": 1203},
        {"value": 14, "repo": "sample-auth", "pr_number": 655}
      ],
      "most_commented_pr": [
        {"value": 64, "repo": "sample-api", "pr_number": 482},
        {"value": 51, "repo": "sample-web", "pr_number": 1203}
      ],
      "most_commits_pr": [
        {"value": 64, "repo": "sample-web", "pr_number": 910},
        {"value": 48, "repo": "sample-api", "pr_number": 482}
      ],
      "most_lines_deleted_pr": [
        {"value": 8120, "repo": "sample-infra", "pr_number": 377},
        {"value": 5400, "repo": "sample-web", "pr_number": 910}
      ],
      "most_reviewed_pr": [
        {"value": 31, "repo": "sample-auth", "pr_number": 655},
        {"value": 27, "repo": "sample-api", "pr_number": 482}
      ],
      "busiest_day": [
        {"value": 87, "date": "2026-03-14", "merged_prs": 12},
        {"value": 74, "date": "2026-10-02", "merged_prs": 9}
      ],
      "busiest_month": [
        {"value": 412, "month": "2026-03", "merged_prs": 38},
        {"value": 390, "month": "2026-10", "merged_prs": 33}
      ],
      "longest_commit_streak": [
        {"value": 19, "from": "2026-03-02", "to": "2026-03-20"},
        {"value": 14, "from": "2026-09-07", "to": "2026-09-20"}
      ],
      "longest_merge_streak": [
        {"value": 11, "from": "2026-06-01", "to": "2026-06-11"},
        {"value": 8, "from": "2026-10-05", "to": "2026-10-12"}
      ]
    },
    "group:alpha": {
      "longest_comment_chain": [{"value": 23, "repo": "sample-api", "pr_number": 482}],
      "most_commented_pr": [{"value": 64, "repo": "sample-api", "pr_number": 482}],
      "most_commits_pr": [{"value": 48, "repo": "sample-api", "pr_number": 482}],
      "most_lines_deleted_pr": [{"value": 5400, "repo": "sample-web", "pr_number": 910}],
      "most_reviewed_pr": [{"value": 31, "repo": "sample-auth", "pr_number": 655}],
      "busiest_day": [{"value": 61, "date": "2026-03-14", "merged_prs": 8}],
      "busiest_month": [{"value": 280, "month": "2026-03", "merged_prs": 25}],
      "longest_commit_streak": [{"value": 15, "from": "2026-03-02", "to": "2026-03-16"}],
      "longest_merge_streak": [{"value": 9, "from": "2026-06-01", "to": "2026-06-09"}]
    }
  }
}
```
In `data-sample/README.md`, update the `derived/` line to also name `curiosities.json`.

- [ ] **Step 7: Spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`: (a) section 7.6, in the **Curiosities.** bullet, add at its end: `Curiosity datasets are lists of records best first; a record carries `value` and, depending on the curiosity, `repo`, `pr_number`, `date`, `month`, `from`, `to` or `merged_prs`, never people or PR titles.`; (b) section 7.4, add these rows to the curiosities table: `Busiest month` (commits per month), `Longest commit streak` and `Longest merge streak` (consecutive days) and `Most lines deleted in one PR` (enriched); (c) section 13 `type.yml` bullet: change `A param named `names` is a data reference that must resolve to a list.` to `Params named `names` and `records` are data references that must resolve to a list.`

- [ ] **Step 8: Run everything**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src tests docs data-sample
git commit -m "Define the curiosity datasets, validate records lists and add sample data" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The `curiosity` scene type

**Interfaces:**
- Consumes: `presets.format`, `presets.lookup`, `presets.isPartial`, `presets.fadeIn`, `presets.swellIn`; helpers in `tests-js/helpers.js` (`makeEl`, `loadRenderer`, `fakeTimeline`, `find`; the stub's `makeEl` elements have `append`, `children`, `className`, `textContent`, `style`).
- Produces:
  - `presets.formatDate(iso, withWeekday = true)`: `"2026-03-14"` -> `"Saturday 14 March"` / `"14 March"` (en-GB, UTC); anything not `YYYY-MM-DD` is returned unchanged.
  - `presets.formatMonth(iso)`: `"2026-03"` -> `"March"` (en-GB, UTC); anything not `YYYY-MM` returned unchanged.
  - `presets.fillTemplate(template, record)`: placeholder replacement exactly as in Global Constraints.
  - Scene type `curiosity`: params `teaser` (string), `records` (data reference to a list), `unit` (string), optional `context` (template string) and `value_key` (default `"value"`); default duration 6 s. DOM: `div.tw-cur` > `div.tw-cur-teaser`, `div.tw-cur-value`, `div.tw-cur-unit`, optional `div.tw-cur-partial`, optional `div.tw-cur-context`.

- [ ] **Step 1: Write the failing tests**

Append to `tests-js/presets.test.js`:
```js
test("formatDate and formatMonth read ISO values in UTC, in English", () => {
  assert.strictEqual(presets.formatDate("2026-03-14"), "Saturday 14 March");
  assert.strictEqual(presets.formatDate("2026-03-14", false), "14 March");
  assert.strictEqual(presets.formatDate("2026-12-31", false), "31 December");
  assert.strictEqual(presets.formatMonth("2026-03"), "March");
  assert.strictEqual(presets.formatMonth("2026-12"), "December");
  assert.strictEqual(presets.formatDate("tomorrow"), "tomorrow");        // not an ISO date: unchanged
  assert.strictEqual(presets.formatMonth("2026-13"), "2026-13");          // impossible month: unchanged
});

test("fillTemplate fills record fields with the right formats", () => {
  const record = { value: 1234, repo: "sample-api", pr_number: 4821, date: "2026-03-14", from: "2026-03-02", to: "2026-03-20", month: "2026-03", merged_prs: 1500 };
  assert.strictEqual(presets.fillTemplate("in {repo}, pull request #{pr_number}", record), "in sample-api, pull request #4821");
  assert.strictEqual(presets.fillTemplate("on {date}", record), "on Saturday 14 March");
  assert.strictEqual(presets.fillTemplate("from {from} to {to}", record), "from 2 March to 20 March");
  assert.strictEqual(presets.fillTemplate("in {month}, {merged_prs} merged", record), "in March, 1,500 merged");
  assert.strictEqual(presets.fillTemplate("{value} things", record), "1,234 things");
  assert.strictEqual(presets.fillTemplate("{missing}|{repo}", record), "|sample-api");   // unknown fields become empty
  assert.strictEqual(presets.fillTemplate("no placeholders", record), "no placeholders");
});
```
`tests-js/curiosity.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = {
  "curiosities.longest_comment_chain": [
    { value: 23, repo: "sample-api", pr_number: 482 },
    { value: 19, repo: "sample-web", pr_number: 1203 },
  ],
};
const PARAMS = {
  teaser: "The longest conversation",
  records: "curiosities.longest_comment_chain",
  unit: "comments in one review thread",
  context: "in {repo}, pull request #{pr_number}",
};
const round2 = (n) => Math.round(n * 100) / 100;

function render(params, data = DATA, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("curiosity").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

test("the scene shows the teaser, the first record's number, the unit and the filled context", () => {
  const { tl, container, result } = render(PARAMS);
  assert.strictEqual(result, tl);
  const wrap = container.children[0];
  assert.strictEqual(wrap.className, "tw-cur");
  assert.deepStrictEqual(wrap.children.map((c) => c.className), ["tw-cur-teaser", "tw-cur-value", "tw-cur-unit", "tw-cur-context"]);
  assert.deepStrictEqual(wrap.children.map((c) => c.textContent), [
    "The longest conversation", "23", "comments in one review thread", "in sample-api, pull request #482",
  ]);
});

test("the number appears at its final value and swells, with no count-up", () => {
  const { tl, container } = render(PARAMS);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).length, 0);
  const swells = tl.calls.filter((c) => c.kind === "fromTo");
  assert.strictEqual(swells.length, 1);
  assert.strictEqual(swells[0].targets, find(container, "tw-cur-value")[0]);
  assert.strictEqual(round2(swells[0].at), 0.9);
  assert.ok(swells[0].vars.scale > 1);
});

test("the teaser, unit and context fade in one after another", () => {
  const { tl, container } = render(PARAMS);
  const fades = tl.calls.filter((c) => c.kind === "from" && !Array.isArray(c.targets));
  assert.deepStrictEqual(fades.map((c) => c.targets.className), ["tw-cur-teaser", "tw-cur-unit", "tw-cur-context"]);
  assert.deepStrictEqual(fades.map((c) => round2(c.at)), [0, 1.35, 1.85]);
});

test("a different value_key picks another number from the record", () => {
  const data = { "curiosities.busiest_day": [{ value: 87, merged_prs: 12, date: "2026-03-14" }] };
  const { container } = render({ teaser: "T", records: "curiosities.busiest_day", unit: "pull requests merged", value_key: "merged_prs", context: "on {date}" }, data);
  assert.strictEqual(find(container, "tw-cur-value")[0].textContent, "12");
  assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "on Saturday 14 March");
});

test("no context param means no context element", () => {
  const { container } = render({ teaser: "T", records: PARAMS.records, unit: "u" });
  assert.strictEqual(find(container, "tw-cur-context").length, 0);
});

test("a missing record shows a dash and no context", () => {
  [{}, { "curiosities.longest_comment_chain": [] }, { "curiosities.longest_comment_chain": "x" }].forEach((data) => {
    const { container } = render(PARAMS, data);
    assert.strictEqual(find(container, "tw-cur-value")[0].textContent, "–");
    assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "");
  });
});

test("a partial dataset gets a badge that fades in with the unit", () => {
  const { tl, container } = render(PARAMS, DATA, ["curiosities.longest_comment_chain"]);
  const badge = find(container, "tw-cur-partial")[0];
  assert.ok(badge);
  const fade = tl.calls.find((c) => c.kind === "from" && Array.isArray(c.targets) && c.targets.includes(badge));
  assert.strictEqual(round2(fade.at), 1.35);
  assert.strictEqual(find(render(PARAMS, DATA, []).container, "tw-cur-partial").length, 0);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL: `presets.formatDate`, `formatMonth` and `fillTemplate` do not exist; no `curiosity` renderer.

- [ ] **Step 3: Add the template helpers to `presets.js`**

In `web/presets/presets.js` add these functions (before the `const api` line) and add `formatDate, formatMonth, fillTemplate` to the exported `api` object (keep every existing export):
```js
  const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  const DAY_SHORT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", timeZone: "UTC" });
  const MONTH = new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" });

  // "2026-03-14" -> "Saturday 14 March" (or "14 March" without the weekday); other values are returned unchanged.
  function formatDate(iso, withWeekday = true) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
    if (!m) return iso;
    const date = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (date.getUTCMonth() !== +m[2] - 1 || date.getUTCDate() !== +m[3]) return iso;     // impossible date
    return (withWeekday ? DAY : DAY_SHORT).format(date);
  }

  // "2026-03" -> "March"; other values are returned unchanged.
  function formatMonth(iso) {
    const m = /^(\d{4})-(\d{2})$/.exec(String(iso));
    if (!m || +m[2] < 1 || +m[2] > 12) return iso;
    return MONTH.format(new Date(Date.UTC(+m[1], +m[2] - 1, 1)));
  }

  // Replaces {key} in a template with the record's value, formatted by key.
  const FIELD_FORMATS = {
    date: (v) => formatDate(v, true),
    from: (v) => formatDate(v, false),
    to: (v) => formatDate(v, false),
    month: (v) => formatMonth(v),
  };
  function fillTemplate(template, record) {
    return String(template).replace(/\{(\w+)\}/g, (_, key) => {
      const value = record[key];
      if (value === undefined || value === null) return "";
      if (FIELD_FORMATS[key]) return FIELD_FORMATS[key](String(value));
      if (/_number$/.test(key)) return String(value);                    // ids are never given thousands separators
      return typeof value === "number" ? format(value) : String(value);
    });
  }
```

- [ ] **Step 4: Create the scene type**

`web/scene-types/curiosity/type.yml`:
```yaml
name: curiosity
default_duration: 6
required_params: [teaser, records, unit]
```
`web/scene-types/curiosity/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const list = presets.lookup(data, params.records);
    const first = Array.isArray(list) && list.length > 0 ? list[0] : null;
    const record = first !== null && typeof first === "object" ? first : null;
    const valueKey = typeof params.value_key === "string" && params.value_key !== "" ? params.value_key : "value";

    const part = (className, text) => {
      const el = document.createElement("div");
      el.className = className;
      el.textContent = text;
      return el;
    };

    const raw = record ? record[valueKey] : undefined;
    const teaser = part("tw-cur-teaser", params.teaser);
    // Shown at its final value straight away: the swell is the only animation.
    const value = part("tw-cur-value", typeof raw === "number" ? presets.format(raw) : "–");
    const unit = part("tw-cur-unit", params.unit);
    const badge = presets.isPartial(partial, params.records) ? part("tw-cur-partial", "partial data") : null;
    const hasContext = typeof params.context === "string" && params.context !== "";
    const context = hasContext ? part("tw-cur-context", record ? presets.fillTemplate(params.context, record) : "") : null;

    const wrap = document.createElement("div");
    wrap.className = "tw-cur";
    wrap.append(...[teaser, value, unit, badge, context].filter(Boolean));
    container.append(wrap);

    presets.fadeIn(tl, teaser, 0, 0.6);
    presets.swellIn(tl, value, 0.9);
    presets.fadeIn(tl, badge ? [unit, badge] : unit, 1.35, 0.4);
    if (context) presets.fadeIn(tl, context, 1.85, 0.5);
    return tl;
  },
};
```

- [ ] **Step 5: Style the scene**

Append to `web/player/player.css`:
```css
.tw-cur { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0.6rem; }
.tw-cur-teaser { font-size: clamp(1.6rem, 5vw, 3rem); font-weight: 700; margin-bottom: 0.6rem; }
.tw-cur-value { font-size: clamp(5rem, 20vw, 13rem); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; color: var(--tw-accent); }
.tw-cur-unit { font-size: clamp(1.2rem, 3.5vw, 2rem); opacity: 0.85; }
.tw-cur-partial { font-size: 0.8rem; color: var(--tw-warning); }
.tw-cur-context { margin-top: 1.2rem; font-size: clamp(1rem, 2.6vw, 1.5rem); opacity: 0.7; }
```

- [ ] **Step 6: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && grep -nE '#[0-9a-fA-F]{3,8}\b' web/player/player.css`
Expected: all pass; the grep lists only the `:root` block.

- [ ] **Step 7: Syntax-check and build**

Run: `node --check web/presets/presets.js && cp web/scene-types/curiosity/render.js "$TMPDIR/curiosity.mjs" && node --check "$TMPDIR/curiosity.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-cur"`
Expected: no syntax errors; `built .../tw-cur/year-wrapped/index.html`.

- [ ] **Step 8: Commit**

```bash
git add web tests-js
git commit -m "Add the curiosity scene type and date and template helpers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The scenes and their place in the script

**Interfaces:**
- Consumes: the `curiosity` type and the `curiosities.*` sample data (Tasks 1 and 2).
- Produces: nine scene files and the script order below.

- [ ] **Step 1: Create the scene files**

Create these files in `scenes/`. Each has the shape shown for the first; only the values differ.

`scenes/curiosity-busiest-month.yml`:
```yaml
id: curiosity-busiest-month
title: Our busiest month
type: curiosity
requires:
  - dataset: curiosities.busiest_month
    fields: [value, month, merged_prs]
    allow_partial: false
params:
  teaser: "Our busiest month"
  records: curiosities.busiest_month
  unit: "commits"
  context: "in {month}, with {merged_prs} pull requests merged"
```
`scenes/curiosity-busiest-day.yml`: id `curiosity-busiest-day`, title `Our busiest day`, dataset `curiosities.busiest_day`, fields `[value, date, merged_prs]`, `allow_partial: false`; params: teaser `"Our busiest day"`, records `curiosities.busiest_day`, unit `"commits"`, context `"on {date}, with {merged_prs} pull requests merged"`.
`scenes/curiosity-longest-streak.yml`: id `curiosity-longest-streak`, title `Our longest streak`, dataset `curiosities.longest_commit_streak`, fields `[value, from, to]`, `allow_partial: false`; params: teaser `"Our longest streak"`, records `curiosities.longest_commit_streak`, unit `"days in a row with a commit"`, context `"from {from} to {to}"`.
`scenes/curiosity-longest-conversation.yml`: id `curiosity-longest-conversation`, title `The longest conversation`, dataset `curiosities.longest_comment_chain`, fields `[value, repo, pr_number]`, `allow_partial: false`; params: teaser `"The longest conversation"`, records `curiosities.longest_comment_chain`, unit `"comments in one review thread"`, context `"in {repo}, pull request #{pr_number}"`.
`scenes/curiosity-most-reviewed-pr.yml`: id `curiosity-most-reviewed-pr`, title `The most reviewed pull request`, dataset `curiosities.most_reviewed_pr`, fields `[value, repo, pr_number]`, `allow_partial: false`; params: teaser `"The most reviewed pull request"`, records `curiosities.most_reviewed_pr`, unit `"reviews"`, context `"in {repo}, pull request #{pr_number}"`.
`scenes/curiosity-most-commits-pr.yml`: id `curiosity-most-commits-pr`, title `The pull request that kept going`, dataset `curiosities.most_commits_pr`, fields `[value, repo, pr_number]`, **`allow_partial: true`** with the comment `# needs enriched pull request records`; params: teaser `"The pull request that kept going"`, records `curiosities.most_commits_pr`, unit `"commits in one pull request"`, context `"in {repo}, pull request #{pr_number}"`.
`scenes/curiosity-spring-cleaning.yml`: id `curiosity-spring-cleaning`, title `Spring cleaning`, dataset `curiosities.most_lines_deleted_pr`, fields `[value, repo, pr_number]`, **`allow_partial: true`** (same comment); params: teaser `"Spring cleaning"`, records `curiosities.most_lines_deleted_pr`, unit `"lines deleted in one pull request"`, context `"in {repo}, pull request #{pr_number}"`.
Two scenes kept ready but NOT used in the script:
`scenes/curiosity-longest-merge-streak.yml`: id `curiosity-longest-merge-streak`, title `Our longest merge streak`, dataset `curiosities.longest_merge_streak`, fields `[value, from, to]`, `allow_partial: false`; params: teaser `"Our longest merge streak"`, records `curiosities.longest_merge_streak`, unit `"days in a row with a merged pull request"`, context `"from {from} to {to}"`.
`scenes/curiosity-most-commented-pr.yml`: id `curiosity-most-commented-pr`, title `The most talked-about pull request`, dataset `curiosities.most_commented_pr`, fields `[value, repo, pr_number]`, `allow_partial: false`; params: teaser `"The most talked-about pull request"`, records `curiosities.most_commented_pr`, unit `"comments"`, context `"in {repo}, pull request #{pr_number}"`.

- [ ] **Step 2: Update the script**

In `scripts/year-wrapped.yml` replace the line `  # 4. curiosities will go here` with these entries (each with `on_missing_data: skip` and the short comment `# until the aggregator produces it, the scene is skipped`; keep the YAML valid, one entry per scene):
```yaml
  - scene: curiosity-busiest-month        # 4. curiosities: rhythm...
    on_missing_data: skip
  - scene: curiosity-busiest-day
    on_missing_data: skip
  - scene: curiosity-longest-streak
    on_missing_data: skip
  - scene: curiosity-longest-conversation   # ...collaboration...
    on_missing_data: skip
  - scene: curiosity-most-reviewed-pr
    on_missing_data: skip
  - scene: curiosity-most-commits-pr        # ...and the big changes
    on_missing_data: skip
  - scene: curiosity-spring-cleaning
    on_missing_data: skip
```
Keep every other entry as it is (the numbers at the start, then the recap, then these, then `repos-touched`, `we-changed-the-code`, `how-many-of-us`).

- [ ] **Step 3: Update the tests that list the scenes**

Read `tests/scenes/test_build.py` and `tests/scenes/test_validate.py` and update every assertion that depends on the `year-wrapped` scene list: the payload scene ids in order `["we-shipped", "we-looked-after-each-other", "year-in-numbers", "curiosity-busiest-month", "curiosity-busiest-day", "curiosity-longest-streak", "curiosity-longest-conversation", "curiosity-most-reviewed-pr", "curiosity-most-commits-pr", "curiosity-spring-cleaning", "repos-touched", "we-changed-the-code", "how-many-of-us"]`; the durations `[7.0, 6.0, 8.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 8.0, 6.0, 10.0]`; `inlined scene types` assertions gain `'TeamWrapped.sceneTypes["curiosity"]' in html`; the "delivery_volume.json deleted" test still skips `["year-in-numbers", "we-changed-the-code"]` and its remaining payload ids now include the seven curiosity scenes (they do not need `delivery_volume`); in `test_validate.py`'s statuses dict add the seven new scenes: `curiosity-most-commits-pr` and `curiosity-spring-cleaning` are `supported` (the sample marks no curiosity dataset partial), the other five `supported`; `curiosity-longest-merge-streak` and `curiosity-most-commented-pr` are not in the script so they do not appear. Add one test in `tests/scenes/test_validate.py` that validates a tiny private script containing every `curiosity-*` scene file (including the two unused ones) against `data-sample` with `resolve_and_validate` and asserts all nine are `supported`, so the unused scene files stay valid. Do not weaken any assertion.

- [ ] **Step 4: Run everything**

Run: `python3 -m pytest -q && node --test tests-js/ && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all pass; validate lists thirteen scenes, each supported or partial.

- [ ] **Step 5: Build once**

Run: `PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-cur2"`
Expected: `built .../tw-cur2/year-wrapped/index.html`.

- [ ] **Step 6: Commit**

```bash
git add scenes scripts tests
git commit -m "Add the curiosity scenes and place them in the Year Wrapped" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- The aggregator that produces the curiosity datasets from real data (until then each scene is skipped on real data).
- Viewing the scenes in a browser: the controller checks them by hand.
- A leaderboard (showing ranks 2 and 3) and other curiosities (first and last commit, smallest PR, night owl, most-active repository, review marathon).
