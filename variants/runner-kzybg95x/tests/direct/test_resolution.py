import pytest
from helpers import *
from test_registration import reg


def setup_event(ta, direct_vm, urls=URLS2, pages=None, llm_json=None):
    reg(ta, source_urls=urls)
    mock_pages(direct_vm, pages or PAGES_OK)
    direct_vm.mock_llm(r"PROPOSITION", llm_json or sup2())


def test_confirmed_true_end_to_end(ta, direct_vm, mod):
    setup_event(ta, direct_vm)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    assert direct_vm.run_validator() is True
    ev = ta.get_event(1)
    assert ev["lifecycle_status"] == "RESOLVED_TRUE" and ev["final_outcome"] == "CONFIRMED_TRUE"
    assert ev["outcome_reason"] == 0 and ev["resolution_timestamp"] == NOW_TS
    assert [e["classification"] for e in ev["evidence"]] == [1, 1]
    assert [e["independence_group"] for e in ev["evidence"]] == [0, 1]
    assert ev["evidence"][0]["publisher_host"] == "gov.example"
    assert len(ev["evidence_commitment"]) == 64 and len(ev["result_commitment"]) == 64
    expected = mod._result_commitment(1, PROP, START, END, URLS2.split(), ev["evidence_commitment"], 1, 0)
    assert ev["result_commitment"] == expected
    assert ta.get_event_status(1) == "RESOLVED_TRUE"


def test_confirmed_false_needs_two_independent_contradictions(ta, direct_vm):
    setup_event(ta, direct_vm, llm_json=llm([src(0, "CONTRADICTS", excerpt=EX_A), src(1, "CONTRADICTS", "NEWS_SECONDARY", EX_B)]))
    assert ta.resolve_event(1) == "CONFIRMED_FALSE"
    assert ta.get_event(1)["lifecycle_status"] == "RESOLVED_FALSE"


@pytest.mark.parametrize("sources,reason", [
    ([src(0, "SUPPORTS", excerpt=EX_A), src(1, "CONTEXT_ONLY")], 1),
    ([src(0, "INSUFFICIENT"), src(1, "INSUFFICIENT")], 1),
    ([src(0, "SUPPORTS", excerpt=EX_A), src(1, "CONTRADICTS", excerpt=EX_B)], 3),
    ([src(0, "CONTRADICTS", excerpt=EX_A), src(1, "CONTEXT_ONLY")], 1),
])
def test_inconclusive_reasons(ta, direct_vm, sources, reason):
    setup_event(ta, direct_vm, llm_json=llm(sources))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert ev["lifecycle_status"] == "INCONCLUSIVE" and ev["outcome_reason"] == reason


def test_not_assessable_is_inconclusive_reason_4(ta, direct_vm):
    setup_event(ta, direct_vm, llm_json=llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", excerpt=EX_B)], assessable=False))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert ev["outcome_reason"] == 4 and all(e["classification"] == 4 for e in ev["evidence"])
    assert direct_vm.run_validator() is True


def test_unavailable_sources_never_mean_false(ta, direct_vm):
    pages = {r"gov\.example": (404, "not found"), r"news\.example\.org": (503, "down")}
    reg(ta); mock_pages(direct_vm, pages)  # no LLM mock needed: no readable source
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert ev["outcome_reason"] == 2 and [e["retrieval_status"] for e in ev["evidence"]] == [1, 1]
    assert all(e["classification"] == 5 for e in ev["evidence"])
    assert ev["lifecycle_status"] != "RESOLVED_FALSE"


def test_empty_body_and_fetch_error_are_unavailable(ta, direct_vm):
    reg(ta)
    mock_pages(direct_vm, {r"gov\.example": (200, ""), r"news\.example\.org": (200, "<html>  </html>")})
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    assert [e["retrieval_status"] for e in ta.get_event(1)["evidence"]] == [2, 2]


def test_one_unavailable_one_supporting_is_inconclusive(ta, direct_vm):
    pages = dict(PAGES_OK); pages[r"news\.example\.org"] = (500, "boom")
    setup_event(ta, direct_vm, pages=pages, llm_json=llm([src(0, "SUPPORTS", excerpt=EX_A)]))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    assert ta.get_event(1)["outcome_reason"] == 1


def test_same_host_counts_as_one_independent_group(ta, direct_vm):
    urls = "https://www.gov.example/a/one-page https://gov.example/b/two-page"
    pages = {r"gov\.example": (200, "<p>" + TEXT_A + "</p>")}
    setup_event(ta, direct_vm, urls=urls, pages=pages,
                llm_json=llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", excerpt=EX_A)]))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert [e["independence_group"] for e in ev["evidence"]] == [0, 0] and ev["outcome_reason"] == 1


def test_syndicated_copy_merges_groups(ta, direct_vm):
    setup_event(ta, direct_vm, llm_json=llm([src(0, "SUPPORTS", excerpt=EX_A, same=[1]), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)]))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    assert [e["independence_group"] for e in ta.get_event(1)["evidence"]] == [0, 0]


def test_fabricated_excerpt_is_degraded_not_trusted(ta, direct_vm):
    setup_event(ta, direct_vm, llm_json=llm([src(0, "SUPPORTS", excerpt="a sentence that is nowhere in the page"), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)]))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert ev["evidence"][0]["classification"] == 4 and ev["evidence"][0]["excerpt"] == ""


def test_title_and_dates(ta, direct_vm):
    pages = dict(PAGES_OK); pages[r"gov\.example"] = (200, "<title>Law 42 notice</title><p>" + TEXT_A + "</p>")
    setup_event(ta, direct_vm, pages=pages, llm_json=llm([
        src(0, "SUPPORTS", excerpt=EX_A, title="Law 42 notice", pub="2026-03-01", upd="2999-01-01"),
        src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B, title="Invented title", pub="garbage")]))
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    e0, e1 = ta.get_event(1)["evidence"]
    assert e0["title"] == "Law 42 notice" and e0["publication_timestamp"] == START
    assert e0["update_timestamp"] == 0          # future date rejected
    assert e1["title"] == "" and e1["publication_timestamp"] == 0


def test_markup_and_quote_normalization(ta, direct_vm):
    pages = dict(PAGES_OK)
    pages[r"gov\.example"] = (200, "<script>var x=1;</script><style>p{}</style><p>The Ministry\u2019s  \n  decision: <b>Law 42</b> was published on 1 March 2026</p>")
    setup_event(ta, direct_vm, pages=pages, llm_json=llm([
        src(0, "SUPPORTS", excerpt="The Ministry's decision: Law 42 was published"), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)]))
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"


@pytest.mark.parametrize("bad", [
    "[]", '{"proposition_assessable": "yes", "sources": []}', '{"proposition_assessable": true, "sources": []}',
    '{"proposition_assessable": true}', "{}",
    llm([src(0, "MAYBE"), src(1, "SUPPORTS", excerpt=EX_B)]),
    llm([src(0, "SUPPORTS", typ="BLOG"), src(1, "SUPPORTS")]),
    llm([src(0), src(0)]), llm([src(0), src(7)]),
])
def test_malformed_llm_output_is_rejected_and_event_stays_open(ta, direct_vm, bad):
    reg(ta); mock_pages(direct_vm, PAGES_OK); direct_vm.mock_llm(r"PROPOSITION", bad)
    with direct_vm.expect_revert("LLM_ERROR"):
        ta.resolve_event(1)
    assert ta.get_event_status(1) == "OPEN" and ta.get_event(1)["evidence"] == []


def test_resolution_errors(ta, direct_vm):
    with direct_vm.expect_revert("event not found"):
        ta.resolve_event(1)
    setup_event(ta, direct_vm)
    ta.resolve_event(1)
    with direct_vm.expect_revert("event is not open"):
        ta.resolve_event(1)
    assert ta.get_event(1)["lifecycle_status"] == "RESOLVED_TRUE"


def test_resolution_only_reads_registered_urls(ta, direct_vm):
    reg(ta)
    seen = []
    mock_pages(direct_vm, PAGES_OK); direct_vm.mock_llm(r"PROPOSITION", sup2())
    ta.resolve_event(1)
    prompt_urls = [e for e in ta.get_event(1)["source_urls"]]
    assert prompt_urls == URLS2.split()


def test_interleaved_events_keep_their_own_results(ta, direct_vm):
    reg(ta, source_urls=URLS2)                                     # event 1 -> TRUE
    reg(ta, proposition="The Court issued ruling 7 on 2026-03-01 in the Supreme Court.",
        source_urls="https://courts.example.org/r7-aa https://paper.example.com/r7-bb")   # event 2 -> FALSE
    mock_pages(direct_vm, {**PAGES_OK,
        r"courts\.example\.org": (200, "<p>The ruling 7 was never issued by the Supreme Court.</p>"),
        r"paper\.example\.com": (200, "<p>No such ruling 7 exists; the Supreme Court denies it.</p>")})
    direct_vm.mock_llm(r"ruling 7", llm([src(0, "CONTRADICTS", excerpt="was never issued by the Supreme Court"), src(1, "CONTRADICTS", "NEWS_SECONDARY", "No such ruling 7 exists")]))
    direct_vm.mock_llm(r"Law 42", sup2())
    assert ta.resolve_event(2) == "CONFIRMED_FALSE"
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    assert ta.get_event(1)["final_outcome"] == "CONFIRMED_TRUE" and ta.get_event(2)["final_outcome"] == "CONFIRMED_FALSE"
    assert ta.get_event(1)["evidence"][0]["publisher_host"] == "gov.example"
    assert ta.get_event(2)["evidence"][0]["publisher_host"] == "courts.example.org"


def test_reverification_links_new_event_and_keeps_parent(ta, direct_vm):
    reg(ta)
    with direct_vm.expect_revert("parent event is still open"):
        reg(ta, parent_event_id=1)
    mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"PROPOSITION", llm([src(0, "INSUFFICIENT"), src(1, "INSUFFICIENT")]))
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    parent_before = ta.get_event(1)
    with direct_vm.expect_revert("keep the parent proposition"):
        reg(ta, parent_event_id=1, proposition="A completely different proposition about something else.")
    assert reg(ta, parent_event_id=1, source_urls=URLS3) == 2
    assert ta.get_event(2)["parent_event_id"] == 1 and ta.get_event(2)["lifecycle_status"] == "OPEN"
    assert ta.get_event(1) == parent_before
