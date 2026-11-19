import json
import os
import re
import shutil
import subprocess

import pytest
from helpers import *
from test_registration import reg


# ============================ URL, publisher identity and counters ============================
@pytest.mark.parametrize("url,ok", [
    ("https://example.org/a1", True), ("https://sub.example.org:8443/a?b=1#c", True),
    ("https://EXAMPLE.org/Path", True), ("https://example.org", True),
    ("http://example.org/a1", False), ("ftp://example.org/a1", False), ("https://localhost/abc", False),
    ("https://10.0.0.1/abc", False), ("https://a@example.org/abc", False), ("https://exa mple.org/abc", False),
    ("https://-bad.example.org/x", False), ("https://example..org/abc", False),
    ("https://example.org:0/abc", False), ("https://example.org:abc/x", False),
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


@pytest.mark.parametrize("host,expected", [
    ("example.org", "example.org"), ("news.example.org", "example.org"), ("a.b.example.org", "example.org"),
    ("bbc.co.uk", "bbc.co.uk"), ("www.news.bbc.co.uk", "bbc.co.uk"), ("alice.github.io", "alice.github.io"),
    ("deep.alice.github.io", "alice.github.io"), ("gov.example", "gov.example"), ("www.gob.ec", "www.gob.ec"),
    ("ministerio.gob.ec", "ministerio.gob.ec"), ("x.ministerio.gob.ec", "ministerio.gob.ec"),
])
def test_registrable_domain(mod, host, expected):
    assert mod._registrable(host) == expected


def test_publisher_group_registry_is_trusted_static_configuration(mod):
    assert mod._publisher_group("bbc.com") == mod._publisher_group("bbc.co.uk") == "bbc"
    assert mod._publisher_group("reuters.com") == mod._publisher_group("thomsonreuters.com") == "reuters"
    assert mod._publisher_group("unknown.example") == "dom:unknown.example"
    assert isinstance(mod.PUBLISHER_GROUPS, tuple)             # versioned in source, not caller supplied


def test_publisher_identity_cannot_be_supplied_by_the_caller_at_resolution(mod):
    """Expected: resolve_event takes only an event id; identities derive from the registered URLs."""
    abi = json.load(open(os.path.join(os.path.dirname(CONTRACT), "..", "abi.json")))
    assert [p[0] for p in abi["methods"]["resolve_event"]["params"]] == ["event_id"]
    assert not any("publisher" in p[0] or "group" in p[0] for m in abi["methods"].values() for p in m["params"])


def test_id_space_guard(ta, mod):
    import genlayer.gl.vm as v
    mod._check_id_space(1); mod._check_id_space(2**256 - 2)
    for bad in (0, 2**256 - 1, 2**256):
        with pytest.raises(v.UserError):
            mod._check_id_space(bad)


def test_parse_date_bounds(ta, mod):
    assert mod._parse_date("2026-03-01", NOW_TS) == START
    for bad in ("", "x", "2026-13-01", "2026-02-30", "2999-01-01", "1969-12-31", None, 5):
        assert mod._parse_date(bad, NOW_TS) == 0


def test_shingles_are_deterministic_and_bounded(mod):
    t = mod._norm(" ".join("w%d" % k for k in range(10000)))
    s1, s2 = mod._shingles(t), mod._shingles(t)
    assert s1 == s2 and len(s1) <= mod.MAX_SHINGLE_WORDS
    assert mod._near_duplicate(s1, s2) and not mod._near_duplicate({1, 2}, {1, 2})   # too small to judge


# ============================== static source checks ==============================
def test_no_nondeterministic_or_unsupported_primitives_in_the_contract():
    src = open(CONTRACT).read()
    for needle in ("hashlib", "import random", "import os", "import sys", "float(", "import html",
                   "datetime.now", "time.time", "dict()[", "open("):
        assert needle not in src, needle
    assert "run_nondet_unsafe" in src and "run_nondet(" not in src.replace("run_nondet_unsafe(", "")


def test_header_is_exactly_the_target_runner():
    lines = open(CONTRACT).read().split("\n")
    assert lines[0] == "# v0.2.16"
    assert lines[1] == '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'


def test_schema_has_zero_constructor_params_and_the_seven_methods(tmp_path):
    if shutil.which("genvm-lint") is None:
        pytest.skip("genvm-lint not on PATH")
    out = tmp_path / "abi.json"
    r = subprocess.run(["genvm-lint", "schema", CONTRACT, "--output", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text())
    assert d["ctor"] == {"params": [], "kwparams": {}}
    assert set(d["methods"]) == {"register_event", "resolve_event", "get_event", "get_event_status",
                                 "get_event_count", "list_event_ids", "get_limits"}
    assert d == json.load(open(os.path.join(os.path.dirname(CONTRACT), "..", "abi.json")))


# ======================= identity, history and concurrency (no cross-event leakage) =======================
def test_ids_are_monotonic_and_failed_registrations_consume_none(ta, direct_vm):
    with direct_vm.expect_revert("proposition length"):
        reg(ta, proposition="short")
    assert [reg(ta), reg(ta, source_urls=URLS3), reg(ta)] == [1, 2, 3] and ta.get_event_count() == 3


def test_two_callers_register_and_resolve_without_cross_assignment(ta, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_alice; a = reg(ta)
    direct_vm.sender = direct_bob; b = reg(ta, source_urls=URLS3)
    hexof = lambda x: (x.as_hex if hasattr(x, "as_hex") else "0x" + bytes(x).hex()).lower()
    assert ta.get_event(a)["submitter"].lower() == hexof(direct_alice) and ta.get_event(b)["submitter"].lower() == hexof(direct_bob)
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2()); set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    assert ta.get_event_status(2) == "OPEN" and ta.get_event(2)["evidence"] == []


def test_interleaved_resolutions_keep_their_own_results(ta, direct_vm):
    reg(ta)
    reg(ta, proposition="The Court issued ruling 7 on 2026-03-01 in the Supreme Court of Justice.",
        source_urls="https://courts.example.org/r7-aa https://paper.example.com/r7-bb")
    pages = dict(PAGES_OK)
    c1 = "The ruling 7 was never issued by the Supreme Court of Justice."
    c2 = "No such ruling 7 exists; the Supreme Court of Justice denies it."
    pages[r"courts\.example\.org"] = (200, page(c1)); pages[r"paper\.example\.com"] = (200, page(c2))
    mock_pages(direct_vm, pages)
    direct_vm.mock_llm(r"^TASK: SOURCE ANALYSIS(?s:.*)ruling 7", llm([
        src(0, "CONTRADICTS", excerpt="the ruling 7 was never issued by the supreme court of justice"),
        src(1, "CONTRADICTS", "NEWS_SECONDARY", "no such ruling 7 exists; the supreme court of justice denies it")]))
    direct_vm.mock_llm(r"^TASK: SOURCE ANALYSIS", sup2())
    direct_vm.mock_llm(r"^TASK: EXCERPT ENTAILMENT(?s:.*)ruling 7", ent_json({0: "CONTRADICTS", 1: "CONTRADICTS"}))
    direct_vm.mock_llm(r"^TASK: EXCERPT ENTAILMENT", ent_json({0: "SUPPORTS", 1: "SUPPORTS"}))
    set_time(direct_vm, iso_plus(READY_ISO, 700))
    assert ta.resolve_event(2) == "CONFIRMED_FALSE"
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    assert ta.get_event(1)["final_outcome"] == "CONFIRMED_TRUE" and ta.get_event(2)["final_outcome"] == "CONFIRMED_FALSE"
    assert ta.get_event(1)["evidence"][0]["registrable_domain"] == "gov.example"
    assert ta.get_event(2)["evidence"][0]["registrable_domain"] == "example.org"


def test_reverification_links_to_the_parent_and_preserves_it(ta, direct_vm):
    reg(ta)
    with direct_vm.expect_revert("parent event is still open"):
        reg(ta, parent_event_id=1)
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, llm([src(0, "AMBIGUOUS"), src(1, "AMBIGUOUS")]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    parent = ta.get_event(1)
    with direct_vm.expect_revert("keep the parent proposition"):
        reg(ta, parent_event_id=1, proposition="A completely different proposition about something else.")
    assert reg(ta, parent_event_id=1, source_urls=URLS3) == 2
    assert ta.get_event(2)["parent_event_id"] == 1 and ta.get_event(2)["lifecycle_status"] == "OPEN" and ta.get_event(1) == parent


def test_views_do_not_mutate_and_unknown_ids_revert(ta, direct_vm):
    reg(ta)
    before = ta.get_event(1)
    ta.get_event_status(1); ta.get_event_count(); ta.list_event_ids(0, 5); ta.get_limits()
    assert ta.get_event(1) == before
    for bad in (0, 2, 2**64, 2**256 - 1):
        with direct_vm.expect_revert("event not found"):
            ta.get_event(bad)
    assert ta.list_event_ids(2**200, 5) == []


def test_title_and_dates_policy(ta, direct_vm):
    reg(ta)
    pages = dict(PAGES_OK); pages[r"gov\.example"] = (200, "<title>Law 42 notice</title><p>" + TEXT_A + "</p>")
    mock_pages(direct_vm, pages)
    mock_ai(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A, title="Law 42 notice", pub="2026-03-01", upd="2999-01-01"),
                            src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B, title="Invented title", pub="garbage")]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    e0, e1 = ta.get_event(1)["evidence"]
    assert e0["title"] == "law 42 notice" and e0["publication_timestamp"] == START and e0["update_timestamp"] == 0
    assert e1["title"] == "" and e1["publication_timestamp"] == 0


def test_result_commitment_binds_the_registered_record(ta, direct_vm, mod):
    reg(ta); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2()); set_time(direct_vm, READY_ISO)
    ta.resolve_event(1)
    e = ta.get_event(1)
    assert e["result_commitment"] == mod._result_commitment(1, PROP, START, END, URLS2.split(), e["evidence_commitment"], 1, 0)
