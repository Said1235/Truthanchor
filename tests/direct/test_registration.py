import pytest
from helpers import *


def reg(c, **kw):
    args = dict(proposition=PROP, description=DESC, event_start_timestamp=START,
                event_end_timestamp=END, source_urls=URLS2, parent_event_id=0)
    args.update(kw)
    return c.register_event(**args)


def test_zero_arg_deploy_and_initial_state(ta):
    assert ta.get_event_count() == 0
    assert ta.list_event_ids(0, 20) == []
    lim = ta.get_limits()
    assert lim["min_sources"] == 2 and lim["max_sources"] == 5 and lim["criteria_version"] == 1


def test_register_monotonic_ids_and_record(ta, direct_vm, direct_alice, mod):
    assert reg(ta) == 1
    assert reg(ta, source_urls=URLS3) == 2
    assert ta.get_event_count() == 2 and ta.list_event_ids(0, 20) == [1, 2]
    ev = ta.get_event(1)
    assert ev["event_id"] == 1 and ev["lifecycle_status"] == "OPEN" and ev["final_outcome"] == ""
    assert ev["proposition"] == PROP and ev["source_urls"] == URLS2.split()
    assert ev["registration_timestamp"] == NOW_TS and ev["evidence"] == []
    assert ev["evidence_commitment"] == "" and ev["resolution_timestamp"] == 0
    assert ev["parent_event_id"] == 0 and ev["submitter"].lower() == "0x" + bytes(direct_alice).hex()


def test_proposition_is_stored_stripped(ta):
    assert reg(ta, proposition="   " + PROP + "  ") == 1
    assert ta.get_event(1)["proposition"] == PROP


@pytest.mark.parametrize("kw,msg", [
    (dict(proposition=""), "proposition length"),
    (dict(proposition="too short"), "proposition length"),
    (dict(proposition="x" * 301), "proposition length"),
    (dict(description="d" * 1001), "description too long"),
    (dict(event_start_timestamp=END + 1), "start_timestamp must be"),
    (dict(event_end_timestamp=NOW_TS + 1), "already occurred"),
    (dict(event_start_timestamp=-1), "out of range"),
    (dict(event_end_timestamp=2**64), "out of range"),
    (dict(parent_event_id=-1), "out of range"),
    (dict(source_urls=URL_A), "between 2 and 5"),
    (dict(source_urls=""), "between 2 and 5"),
    (dict(source_urls=URL_A + " " + URL_A), "duplicate"),
    (dict(source_urls=URL_A + " https://gov.example/news/law-42/#frag"), "duplicate"),
    (dict(source_urls=URL_A + " http://news.example.org/x1234"), "only https"),
    (dict(source_urls=URL_A + " https://user:pw@news.example.org/x"), "credentials"),
    (dict(source_urls=URL_A + " https://127.0.0.1/some/path"), "ip hosts"),
    (dict(source_urls=URL_A + " https://localhost/some/path"), "invalid url host"),
    (dict(source_urls=URL_A + " https://svc.internal/some/path"), "internal hosts"),
    (dict(source_urls=URL_A + " https://[::1]/some/path"), "ip literals"),
    (dict(source_urls=URL_A + " https://a.example.org:99999/x"), "port"),
    (dict(source_urls=URL_A + " https://news.example.org/" + "p" * 500), "url length"),
    (dict(source_urls=" ".join(["https://s%d.example.org/a1" % i for i in range(6)])), "between 2 and 5"),
    (dict(source_urls=URL_A + " " + "https://news.example.org/\u00e9\u00e9\u00e9"), "printable ascii"),
    (dict(source_urls="a " * 1300), "too long"),
    (dict(parent_event_id=9), "parent event not found"),
])
def test_register_rejections(ta, direct_vm, kw, msg):
    with direct_vm.expect_revert(msg):
        reg(ta, **kw)
    assert ta.get_event_count() == 0


def test_boundary_timestamps_accepted(ta):
    assert reg(ta, event_start_timestamp=0, event_end_timestamp=0) == 1
    assert reg(ta, event_start_timestamp=NOW_TS, event_end_timestamp=NOW_TS) == 2


def test_five_sources_accepted(ta):
    urls = " ".join("https://s%d.example.org/a1" % i for i in range(5))
    assert reg(ta, source_urls=urls) == 1
    assert len(ta.get_event(1)["source_urls"]) == 5


def test_views_reject_unknown_ids(ta, direct_vm):
    with direct_vm.expect_revert("event not found"):
        ta.get_event(1)
    with direct_vm.expect_revert("event not found"):
        ta.get_event_status(7)
    with direct_vm.expect_revert("invalid offset or limit"):
        ta.list_event_ids(0, 21)
    with direct_vm.expect_revert("invalid offset or limit"):
        ta.list_event_ids(0, 0)


def test_views_do_not_mutate(ta):
    reg(ta)
    before = ta.get_event(1)
    ta.get_event_status(1); ta.get_event_count(); ta.list_event_ids(0, 5); ta.get_limits()
    assert ta.get_event(1) == before and ta.get_event_count() == 1
