import pytest
from helpers import *


@pytest.mark.parametrize("url,ok", [
    ("https://example.org/a1", True), ("https://sub.example.org:8443/a?b=1#c", True),
    ("https://EXAMPLE.org/Path", True), ("http://example.org/a1", False), ("ftp://example.org/a1", False),
    ("https://example.org", True), ("https://localhost/abc", False), ("https://10.0.0.1/abc", False),
    ("https://a@example.org/abc", False), ("https://exa mple.org/abc", False), ("https://-bad.example.org/x", False),
    ("https://example..org/abc", False), ("https://example.org:0/abc", False), ("https://example.org:abc/x", False),
])
def test_validate_url(ta, mod, url, ok):
    if ok:
        key, host = mod._validate_url(url)
        assert host == host.lower() and not host.startswith("www.")
    else:
        import genlayer.gl.vm as v
        with pytest.raises(v.UserError):
            mod._validate_url(url)


def test_url_normalization(ta, mod):
    k1 = mod._validate_url("https://www.Example.org:443/a/b/?q=1#frag")[0]
    k2 = mod._validate_url("https://example.org/a/b?q=1")[0]
    assert k1 == k2 == "https://example.org/a/b?q=1"
    assert mod._validate_url("https://example.org:8443/a1")[0] != mod._validate_url("https://example.org/a1")[0]


def test_id_space_guard(ta, mod):
    import genlayer.gl.vm as v
    mod._check_id_space(1); mod._check_id_space(2**256 - 2)
    for bad in (0, 2**256 - 1, 2**256):
        with pytest.raises(v.UserError):
            mod._check_id_space(bad)


@pytest.mark.parametrize("sup,con,unavail,ok,expect", [
    ([], [], False, True, (3, 1)), ([0], [], False, True, (3, 1)), ([0, 1], [], False, True, (1, 0)),
    ([], [0, 1], False, True, (2, 0)), ([], [0], False, True, (3, 1)), ([0], [1], False, True, (3, 3)),
    ([0, 1], [2], False, True, (3, 3)), ([], [], True, True, (3, 2)), ([0], [], True, True, (3, 1)),
    ([0, 1], [], False, False, (3, 4)), ([], [0, 1], False, False, (3, 4)),
])
def test_derive_outcome_truth_table(ta, mod, sup, con, unavail, ok, expect):
    fs = []
    for g in sup:
        fs.append(dict(classification=1, retrieval_status=0, independence_group=g))
    for g in con:
        fs.append(dict(classification=2, retrieval_status=0, independence_group=g))
    if unavail:
        fs.append(dict(classification=5, retrieval_status=1, independence_group=9))
    lc, reason, _s, _c = mod._derive_outcome(ok, fs)
    assert (lc, reason) == expect


def test_absence_of_evidence_never_yields_false(ta, mod):
    import itertools
    for combo in itertools.product([3, 4, 5], repeat=3):
        fs = [dict(classification=c, retrieval_status=0 if c != 5 else 1, independence_group=i) for i, c in enumerate(combo)]
        assert mod._derive_outcome(True, fs)[0] != 2


def test_groups_are_merge_only(ta, mod):
    assert mod._groups(["a", "b", "a"], []) == [0, 1, 0]
    assert mod._groups(["a", "b", "c"], [(2, 1)]) == [0, 1, 1]
    assert mod._groups(["a", "b"], [(0, 1)]) == [0, 0]


def test_commitments_are_stable_and_bound_to_content(ta, mod):
    f = dict(source_id=0, registered_url=URL_A, publisher_host="gov.example", excerpt="Some  Text", classification=1,
             retrieval_status=0, publication_timestamp=0, update_timestamp=0)
    h = mod._source_commitment(1, f)
    assert len(h) == 64 and h == mod._source_commitment(1, dict(f, excerpt="some text"))   # normalized
    for k, v in dict(registered_url=URL_B, classification=2, excerpt="other", publication_timestamp=5).items():
        assert mod._source_commitment(1, dict(f, **{k: v})) != h
    assert mod._source_commitment(2, f) != h


def test_parse_date_bounds(ta, mod):
    assert mod._parse_date("2026-03-01", NOW_TS) == START
    for bad in ("", "x", "2026-13-01", "2026-02-30", "2999-01-01", "1969-12-31", None, 5):
        assert mod._parse_date(bad, NOW_TS) == 0


def test_schema_has_zero_constructor_params(tmp_path):
    import json, shutil, subprocess
    if shutil.which("genvm-lint") is None:
        pytest.skip("genvm-lint not on PATH")
    out = tmp_path / "abi.json"
    r = subprocess.run(["genvm-lint", "schema", CONTRACT, "--output", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text())
    assert d["ctor"] == {"params": [], "kwparams": {}}
    assert set(d["methods"]) == {"register_event", "resolve_event", "get_event", "get_event_status",
                                 "get_event_count", "list_event_ids", "get_limits"}
    assert all("payable" not in m or m["payable"] is False for m in d["methods"].values())
