"""Finding C: temporary failures and premature calls must never finalise an event.

Policy under test (criteria v2):
  * Eligibility: no resolution before earliest = max(event_end + 3600 s, registration + 600 s), by the
    deterministic transaction time, for every caller.
  * TEMPORARY source states (5xx, 408, 425, 429, 404, empty/incomplete 2xx, any web exception) never
    finalise: the attempt is recorded, the event stays OPEN and can be resolved later.
  * Closure condition: after RETRY_CLOSURE_ATTEMPTS recorded attempts AND RETRY_CLOSURE_WINDOW_SECONDS past
    the eligibility time, temporary states are treated as unavailable so the event can close (INCONCLUSIVE
    reason 2, or a conclusive result from the remaining evidence).
  * PERMANENT states (other 4xx, 3xx, oversized) are not retryable and never become factual negatives."""
from datetime import timedelta

import pytest
from helpers import *
from test_registration import reg

EARLIEST_ISO = "2026-11-13T12:10:00+00:00"          # registration + 600 s


def iso_plus(base_iso, seconds):
    from datetime import datetime
    return (datetime.fromisoformat(base_iso) + timedelta(seconds=seconds)).isoformat()


def start(ta, vm, urls=URLS2):
    reg(ta, source_urls=urls)
    return ta.get_event(1)


def assert_still_open_and_retryable(ta, attempts, when=READY_TS):
    e = ta.get_event(1)
    assert e["lifecycle_status"] == "OPEN" and e["final_outcome"] == "" and e["outcome_reason"] == 0
    assert e["resolution_timestamp"] == 0 and e["result_commitment"] == "" and e["evidence_commitment"] == ""
    assert e["evidence"] == []
    assert e["attempt_count"] == attempts and e["last_attempt_timestamp"] == when and e["last_attempt_reason"] == 5
    assert ta.get_event_status(1) == "OPEN"


# ============================ eligibility (premature resolution) ============================
def test_C1_resolution_before_the_eligibility_time_is_rejected_without_any_state_change(ta, direct_vm):
    ev0 = start(ta, direct_vm)
    assert ev0["earliest_resolution_timestamp"] == EARLIEST_TS
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    before = ta.get_event(1)
    for iso in (NOW_ISO, iso_plus(NOW_ISO, 599)):
        set_time(direct_vm, iso)
        with direct_vm.expect_revert("not yet eligible"):
            ta.resolve_event(1)
        assert ta.get_event(1) == before
    assert before["lifecycle_status"] == "OPEN" and before["resolution_timestamp"] == 0 and before["attempt_count"] == 0


def test_C2_immediate_third_party_resolution_does_not_finalise(ta, direct_vm, direct_bob):
    """Expected: a caller other than the creator cannot bypass the eligibility rule."""
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (404, "not yet"), r"news\.example\.org": (404, "not yet")})
    direct_vm.sender = direct_bob
    before = ta.get_event(1)
    with direct_vm.expect_revert("not yet eligible"):
        ta.resolve_event(1)
    assert ta.get_event(1) == before and ta.get_event_status(1) == "OPEN"


def test_C3_eligibility_is_exactly_at_the_earliest_timestamp(ta, direct_vm):
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    set_time(direct_vm, iso_plus(NOW_ISO, 599))
    with direct_vm.expect_revert("not yet eligible"):
        ta.resolve_event(1)
    set_time(direct_vm, EARLIEST_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE" and ta.get_event(1)["resolution_timestamp"] == EARLIEST_TS


def test_C4_settlement_delay_after_event_end_postpones_eligibility(ta, direct_vm):
    recent_end = NOW_TS - 100
    reg(ta, event_start_timestamp=recent_end - 10, event_end_timestamp=recent_end)
    earliest = ta.get_event(1)["earliest_resolution_timestamp"]
    assert earliest == recent_end + 3600
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    set_time(direct_vm, iso_plus(NOW_ISO, 1000))                 # past the 600 s delay, before end + 3600
    with direct_vm.expect_revert("not yet eligible"):
        ta.resolve_event(1)
    set_time(direct_vm, iso_plus(NOW_ISO, 3500))
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"


def test_C5_eligibility_uses_the_transaction_time_not_the_host_clock(mod):
    src = open(CONTRACT).read()
    for needle in ("datetime.now", "time.time", "utcnow", "import time", "date.today"):
        assert needle not in src, needle
    assert "gl.message_raw[\"datetime\"]" in src


def test_C6_every_caller_is_equally_restricted_and_equally_allowed(ta, direct_vm, direct_alice, direct_bob):
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    for who in (direct_alice, direct_bob):
        direct_vm.sender = who
        set_time(direct_vm, NOW_ISO)
        with direct_vm.expect_revert("not yet eligible"):
            ta.resolve_event(1)
    direct_vm.sender = direct_bob
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"


# =============================== temporary failures stay retryable ===============================
TEMP_CASES = [
    ("http_500", (500, "err")), ("http_502", (502, "bad gateway")), ("http_503", (503, "unavailable")),
    ("http_504", (504, "timeout")), ("http_599", (599, "x")), ("http_429", (429, "slow down")),
    ("http_408", (408, "request timeout")), ("http_425", (425, "too early")), ("http_404", (404, "not published yet")),
    ("empty_200", (200, "")), ("blank_markup_200", (200, "<p>   </p>")),
]


@pytest.mark.parametrize("label,resp", TEMP_CASES, ids=[c[0] for c in TEMP_CASES])
def test_C7_all_sources_temporarily_failing_leave_the_event_open_and_retryable(ta, direct_vm, label, resp):
    """Expected: no terminal outcome, no finalization timestamp, no commitments, attempt recorded."""
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": resp, r"news\.example\.org": resp})
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    assert_still_open_and_retryable(ta, 1)
    assert ta.resolve_event(1) == "RETRYABLE"                    # the event stays eligible
    assert ta.get_event(1)["attempt_count"] == 2


def test_C8_all_sources_5xx_is_not_resolved_false_and_not_inconclusive(ta, direct_vm):
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (500, "y")})
    set_time(direct_vm, READY_ISO)
    out = ta.resolve_event(1)
    assert out == "RETRYABLE" and out not in ("CONFIRMED_FALSE", "INCONCLUSIVE")
    assert ta.get_event(1)["lifecycle_status"] not in ("RESOLVED_FALSE", "INCONCLUSIVE")


def test_C9_all_sources_timing_out_or_failing_to_connect_leave_the_event_open(ta, direct_vm, monkeypatch):
    import genlayer.gl.nondet.web as web
    calls = []

    def boom(url, *a, **k):
        calls.append(url)
        raise TimeoutError("read timed out")

    monkeypatch.setattr(web, "get", boom)
    start(ta, direct_vm)
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE" and len(calls) == 2
    assert_still_open_and_retryable(ta, 1)


@pytest.mark.parametrize("exc", [ConnectionError("refused"), OSError("network unreachable"), RuntimeError("weird"), ValueError("bad")])
def test_C10_unknown_web_exceptions_fail_closed_as_retryable(ta, direct_vm, monkeypatch, exc):
    """Expected: an unknown exception is never turned into evidence; it keeps the event open."""
    import genlayer.gl.nondet.web as web

    def boom(url, *a, **k):
        raise exc

    monkeypatch.setattr(web, "get", boom)
    start(ta, direct_vm); set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    assert ta.get_event(1)["lifecycle_status"] == "OPEN"


def test_C11_a_single_available_source_is_insufficient_when_the_others_are_down(ta, direct_vm):
    """Expected: one good page plus a 5xx must not finalise; the unavailable source might contradict."""
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (200, page(TEXT_A)), r"news\.example\.org": (503, "down")})
    mock_ai(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A)]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    assert_still_open_and_retryable(ta, 1)


def test_C12_mixed_sources_with_one_temporary_failure_do_not_finalise_even_with_enough_evidence(ta, direct_vm):
    start(ta, direct_vm, URLS3)
    pages = dict(PAGES_OK); pages[r"other\.example\.net"] = (429, "rate limited")
    mock_pages(direct_vm, pages)
    mock_ai(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    assert_still_open_and_retryable(ta, 1)


def test_C13_retry_after_temporary_failure_resolves_correctly(ta, direct_vm):
    """Expected: sources come back in a later transaction and the event resolves normally."""
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x")})
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    direct_vm.clear_mocks()
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    later = iso_plus(READY_ISO, 3600)
    set_time(direct_vm, later)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    e = ta.get_event(1)
    assert e["lifecycle_status"] == "RESOLVED_TRUE" and e["resolution_timestamp"] == iso_ts(later)
    assert e["attempt_count"] == 1 and len(e["evidence"]) == 2        # history of the earlier attempt preserved


def test_C14_temporary_failure_that_recovers_into_missing_evidence_is_inconclusive_not_false(ta, direct_vm):
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (500, "x"), r"news\.example\.org": (500, "x")})
    set_time(direct_vm, READY_ISO)
    ta.resolve_event(1)
    direct_vm.clear_mocks(); mock_pages(direct_vm, PAGES_OK)
    mock_ai(direct_vm, llm([src(0, "IRRELEVANT"), src(1, "IRRELEVANT")]))
    set_time(direct_vm, iso_plus(READY_ISO, 60))
    assert ta.resolve_event(1) == "INCONCLUSIVE" and ta.get_event(1)["outcome_reason"] == 1


# ================================ closure condition (terminal INCONCLUSIVE) ================================
def burn_attempts(ta, vm, n, first=READY_ISO):
    mock_pages(vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x")})
    t = first
    for k in range(n):
        set_time(vm, t)
        assert ta.resolve_event(1) == "RETRYABLE"
        t = iso_plus(t, 60)
    return t


def test_C15_closure_needs_both_the_attempts_and_the_window(ta, direct_vm):
    start(ta, direct_vm)
    burn_attempts(ta, direct_vm, 3)
    assert ta.get_event(1)["attempt_count"] == 3
    set_time(direct_vm, iso_plus(EARLIEST_ISO, 86399))                  # 3 attempts, window not elapsed
    assert ta.resolve_event(1) == "RETRYABLE" and ta.get_event(1)["attempt_count"] == 4
    set_time(direct_vm, iso_plus(EARLIEST_ISO, 86400))                  # window elapsed AND attempts >= 3
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    e = ta.get_event(1)
    assert e["lifecycle_status"] == "INCONCLUSIVE" and e["outcome_reason"] == 2
    assert [x["retrieval_status"] for x in e["evidence"]] == [4, 4] and all(x["classification"] == 5 for x in e["evidence"])
    assert e["final_outcome"] != "CONFIRMED_FALSE"


def test_C16_window_alone_without_enough_attempts_does_not_close(ta, direct_vm):
    start(ta, direct_vm)
    burn_attempts(ta, direct_vm, 2)
    set_time(direct_vm, iso_plus(EARLIEST_ISO, 90000))
    assert ta.resolve_event(1) == "RETRYABLE"


def test_C17_closure_lets_remaining_evidence_decide(ta, direct_vm):
    """Expected: at closure, a still-failing third source no longer blocks a conclusive result."""
    start(ta, direct_vm, URLS3)
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x"), r"other\.example\.net": (503, "x")})
    for k in range(3):
        set_time(direct_vm, iso_plus(READY_ISO, 60 * k))
        ta.resolve_event(1)
    direct_vm.clear_mocks()
    pages = dict(PAGES_OK); pages[r"other\.example\.net"] = (503, "still down")
    mock_pages(direct_vm, pages)
    mock_ai(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)]))
    set_time(direct_vm, iso_plus(EARLIEST_ISO, 86400))
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"


# ============================================ permanent failures ============================================
@pytest.mark.parametrize("status", [401, 403, 410, 451, 301, 302, 400])
def test_C18_permanent_failures_are_not_retryable_and_never_a_negative_fact(ta, direct_vm, status):
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (status, "x"), r"news\.example\.org": (status, "x")})
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    e = ta.get_event(1)
    assert e["outcome_reason"] == 2 and [x["retrieval_status"] for x in e["evidence"]] == [1, 1]
    assert e["final_outcome"] == "INCONCLUSIVE" and e["attempt_count"] == 0


def test_C19_mixed_permanent_and_temporary_stays_retryable(ta, direct_vm):
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (403, "x"), r"news\.example\.org": (503, "x")})
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"


# ===================================== terminal states are never overwritten =====================================
def test_C20_repeated_resolution_does_not_overwrite_a_finalised_event(ta, direct_vm, direct_bob):
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    first = ta.get_event(1)
    direct_vm.clear_mocks()
    mock_pages(direct_vm, {r"gov\.example": (200, page("Different now. " + EX_A + " is false")), r"news\.example\.org": (503, "x")})
    mock_ai(direct_vm, llm([src(0, "CONTRADICTS", excerpt=EX_A)]))
    for who in (None, direct_bob):
        if who is not None:
            direct_vm.sender = who
        set_time(direct_vm, iso_plus(READY_ISO, 7200))
        with direct_vm.expect_revert("not open"):
            ta.resolve_event(1)
    assert ta.get_event(1) == first


def test_C21_a_retryable_attempt_never_overwrites_or_creates_a_result(ta, direct_vm):
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x")})
    set_time(direct_vm, READY_ISO)
    ta.resolve_event(1)
    assert ta.get_event_count() == 1 and ta.list_event_ids(0, 20) == [1]


def test_C22_inconclusive_terminal_is_overwritten_only_by_a_new_linked_event(ta, direct_vm):
    start(ta, direct_vm)
    mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, llm([src(0, "IRRELEVANT"), src(1, "IRRELEVANT")]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    old = ta.get_event(1)
    assert reg(ta, parent_event_id=1) == 2 and ta.get_event(1) == old and ta.get_event(2)["parent_event_id"] == 1


# ===================================== failed attempts leave no partial state =====================================
def test_C23_validator_disagreement_or_consensus_failure_changes_nothing(ta, direct_vm, monkeypatch):
    import genlayer.gl.vm as glvm
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    set_time(direct_vm, READY_ISO)
    before = ta.get_event(1)

    def no_consensus(*a, **k):
        raise glvm.UserError("consensus not reached")

    monkeypatch.setattr(glvm, "run_nondet_unsafe", no_consensus)
    with direct_vm.expect_revert("consensus not reached"):
        ta.resolve_event(1)
    assert ta.get_event(1) == before


def test_C24_llm_failure_is_not_a_factual_outcome_and_not_a_recorded_attempt(ta, direct_vm):
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"^TASK: SOURCE ANALYSIS", "[]")
    set_time(direct_vm, READY_ISO)
    before = ta.get_event(1)
    with direct_vm.expect_revert("LLM_ERROR"):
        ta.resolve_event(1)
    assert ta.get_event(1) == before


def test_C25_validator_side_temporary_failure_rejects_a_factual_leader_result(ta, direct_vm):
    """Expected: leader saw good pages; the validator's own fetch fails temporarily -> REJECT, not accept."""
    start(ta, direct_vm); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    set_time(direct_vm, READY_ISO)
    ta.resolve_event(1)
    direct_vm.clear_mocks()
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x")})
    assert direct_vm.run_validator() is False


def test_C26_leader_retryable_must_be_confirmed_by_the_validators_own_fetch(ta, direct_vm):
    """Expected: leader says RETRYABLE (all 5xx); validator sees healthy pages -> REJECT."""
    start(ta, direct_vm)
    mock_pages(direct_vm, {r"gov\.example": (503, "x"), r"news\.example\.org": (503, "x")})
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "RETRYABLE"
    direct_vm.clear_mocks(); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2())
    assert direct_vm.run_validator() is False
    direct_vm.clear_mocks(); mock_pages(direct_vm, {r"gov\.example": (500, "y"), r"news\.example\.org": (504, "z")})
    assert direct_vm.run_validator() is True                              # agrees: still temporary


def test_C27_view_exposes_eligibility_and_attempt_metadata(ta, direct_vm):
    e = start(ta, direct_vm)
    for k in ("earliest_resolution_timestamp", "attempt_count", "last_attempt_timestamp", "last_attempt_reason"):
        assert k in e
