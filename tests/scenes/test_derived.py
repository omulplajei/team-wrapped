from team_wrapped.scenes.derived import DerivedData, has_field, resolve_ref


def test_scope_key():
    assert DerivedData.scope_key("all") == "all"
    assert DerivedData.scope_key("alpha") == "group:alpha"
    assert DerivedData.scope_key("group:alpha") == "group:alpha"
    assert DerivedData.scope_key("repo:api") == "repo:api"


def test_dataset_lookup_on_sample(sample_root):
    d = DerivedData(sample_root)
    assert d.dataset("summary.totals", "all")["commits"] == 1240
    assert d.dataset("contributors", "all")["total"] == 13
    assert d.dataset("contributors", "group:alpha")["total"] == 10
    assert d.dataset("summary.nope", "all") is None            # unknown dataset name
    assert d.dataset("review_collab.reviews", "all") is None   # family file does not exist
    assert d.dataset("summary.totals", "group:nope") is None   # unknown scope


def test_partial_datasets_from_meta(sample_root, tmp_path):
    assert DerivedData(sample_root).partial_datasets() == {"delivery_volume.lines"}
    assert DerivedData(tmp_path).partial_datasets() == set()   # no meta.json at all


def test_has_field():
    node = {"total": 3, "by_kind": {"bot": 1},
            "list": [{"kind": "human", "login": "a"}, {"kind": "unlinked"}]}
    assert has_field(node, "total")
    assert has_field(node, "by_kind.bot")
    assert has_field(node, "list.kind")
    assert has_field(node, "list.login")      # present on at least one item
    assert not has_field(node, "list.email")
    assert not has_field(node, "nope")


def test_resolve_ref():
    datasets = {"summary.totals": {"commits": 5}, "contributors": {"total": 2}}
    assert resolve_ref(datasets, "summary.totals.commits") == 5
    assert resolve_ref(datasets, "contributors.total") == 2
    assert resolve_ref(datasets, "summary.totals.nope") is None
    assert resolve_ref(datasets, "other.thing.value") is None


def test_repos_touched_on_sample(sample_root):
    d = DerivedData(sample_root)
    everything = d.dataset("repos.touched", "all")
    assert everything["total"] == 14
    assert len(everything["list"]) == 14
    assert everything["list"][0] == {"name": "sample-analytics"}
    alpha = d.dataset("repos.touched", "group:alpha")
    assert alpha["total"] == 9 and len(alpha["list"]) == 9
