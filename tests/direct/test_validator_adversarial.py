"""Validators must independently verify every decision-bearing field. Forged results below are INTERNALLY
CONSISTENT (valid structure, recomputed fingerprints and commitments, outcome derived from their own
findings), so only independent re-derivation can reject them. A validator that only checked JSON validity,
the outcome, counts or hashes supplied by the leader would accept them (see the naive-validator contrast)."""
import copy
import itertools
import json

import pytest
from helpers import *
from test_registration import reg


@pytest.fixture
def true_result(ta, direct_vm, mod):
    reg(ta); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2()); set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    return captured_result(direct_vm)


def revalidate(vm, analysis, rels=None, pages=None):
    vm.clear_mocks()
    mock_pages(vm, pages or PAGES_OK)
    mock_ai(vm, analysis, rels)
    return vm.run_validator()


def struct_ok(mod, r, urls=None, final=False):
    return mod._check_structure(r, 1, PROP, urls or URLS2.split(), final)


def lie(f):
    return lambda r: f(r["evidence_findings"])


def test_honest_leader_is_accepted(true_result, direct_vm):
    assert direct_vm.run_validator() is True
    assert direct_vm.run_validator(leader_result=true_result) is True


@pytest.mark.parametrize("name,mut", [
    ("flip_classification", lambda fs: fs[0].update(classification=2)),
    ("source_type", lambda fs: fs[0].update(source_type=3)),
    ("publication_date", lambda fs: fs[0].update(publication_timestamp=START)),
    ("update_date", lambda fs: fs[1].update(update_timestamp=START)),
    ("independence_group", lambda fs: fs[1].update(independence_group=0)),
    ("fabricated_excerpt", lambda fs: fs[0].update(excerpt="the ministry personally confirmed everything about the new law")),
    ("excerpt_from_other_source", lambda fs: fs[0].update(excerpt="law 42 was published by the ministry of finance on 1 march 2026")),
    ("fabricated_title", lambda fs: fs[1].update(title="totally invented headline for this page")),
    ("lazy_inconclusive", lambda fs: [f.update(classification=3, excerpt="") for f in fs]),
])
def test_consistent_forgeries_are_rejected_by_independent_rederivation(true_result, direct_vm, mod, name, mut):
    r = forge(mod, true_result, lie(mut))
    assert struct_ok(mod, r) is True, "the forgery must be well formed so that only the validator can catch it"
    assert direct_vm.run_validator(leader_result=r) is False, name


def test_forged_retrieval_status_is_rejected(true_result, direct_vm, mod):
    r = forge(mod, true_result, lie(lambda fs: fs[1].update(retrieval_status=4, classification=5, excerpt="")))
    assert struct_ok(mod, r) and r["proposed_outcome"] == "RETRYABLE"
    assert direct_vm.run_validator(leader_result=r) is False


@pytest.mark.parametrize("name,mut", [
    ("short_excerpt", lambda fs: fs[0].update(excerpt="the ministry published law 42")),
    ("few_words_excerpt", lambda fs: fs[0].update(excerpt="ministry-published-law-42-on-1-march-2026-xx-yy")),
    ("excerpt_not_normalised", lambda fs: fs[0].update(excerpt="The Ministry of Finance published Law 42 on 1 March 2026")),
    ("oversized_excerpt", lambda fs: fs[0].update(excerpt="x " * 200)),
    ("wrong_publisher_group", lambda fs: fs[0].update(publisher_group="bbc")),
    ("wrong_registrable_domain", lambda fs: fs[0].update(registrable_domain="trusted.example.gov")),
    ("excerpt_on_ambiguous", lambda fs: fs[0].update(classification=3)),
])
def test_forgeries_that_violate_the_evidence_policy_fail_the_deterministic_gate(true_result, direct_vm, mod, name, mut):
    r = forge(mod, true_result, lie(mut))
    assert struct_ok(mod, r) is False, name
    assert direct_vm.run_validator(leader_result=r) is False


@pytest.mark.parametrize("name,mut", [
    ("event_id", lambda r: r.update(event_id=2)),
    ("proposition", lambda r: r.update(proposition="A proposition the submitter never registered at all.")),
    ("schema_version", lambda r: r.update(schema_version=1)),
    ("criteria_version", lambda r: r.update(criteria_version=9)),
    ("substituted_url", lambda r: r["evidence_findings"][0].update(registered_url="https://evil.example.org/fake-page")),
    ("missing_source", lambda r: r["evidence_findings"].pop()),
    ("extra_source", lambda r: r["evidence_findings"].append(copy.deepcopy(r["evidence_findings"][0]))),
    ("stale_source_commitment", lambda r: r["evidence_findings"][0].update(source_commitment="0" * 64)),
    ("stale_evidence_commitment", lambda r: r.update(evidence_commitment="f" * 64)),
    ("stale_fingerprint", lambda r: r["evidence_findings"][0].update(excerpt_fingerprint="ab" * 32)),
    ("outcome_only", lambda r: r.update(proposed_outcome="CONFIRMED_FALSE")),
    ("reason_only", lambda r: r.update(outcome_reason=3)),
    ("extra_key", lambda r: r.update(concise_explanation="trust me")),
    ("interval_injected", lambda r: r.update(event_start_timestamp=0, event_end_timestamp=NOW_TS)),
    ("missing_key", lambda r: r.pop("evidence_commitment")),
    ("string_for_int", lambda r: r["evidence_findings"][0].update(classification="1")),
    ("bool_for_int", lambda r: r["evidence_findings"][0].update(source_id=True)),
    ("bad_group_assessment", lambda r: r["independent_source_assessment"].update(independent_supporting_groups=5)),
])
def test_tampered_results_are_rejected(true_result, direct_vm, name, mut):
    r = copy.deepcopy(true_result)
    mut(r)
    assert direct_vm.run_validator(leader_result=r) is False, name


@pytest.mark.parametrize("bad", [None, [], "x", 5, {}, {"evidence_findings": "nope"}])
def test_malformed_leader_results_are_rejected(true_result, direct_vm, bad):
    assert direct_vm.run_validator(leader_result=bad) is False


def test_forced_ambiguous_reason_on_conclusive_evidence_is_rejected(true_result, direct_vm, mod):
    r = copy.deepcopy(true_result); r["proposed_outcome"] = "INCONCLUSIVE"; r["outcome_reason"] = 4
    assert struct_ok(mod, r) is True
    assert direct_vm.run_validator(leader_result=r) is False


# --------------------------- validator-side independent evidence -----------------------------
def test_leader_true_validator_finds_contradiction(true_result, direct_vm):
    assert revalidate(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "CONTRADICTS", "NEWS_SECONDARY", EX_B)])) is False


def test_leader_false_validator_finds_support(ta, direct_vm):
    reg(ta); mock_pages(direct_vm, PAGES_OK)
    mock_ai(direct_vm, llm([src(0, "CONTRADICTS", excerpt=EX_A), src(1, "CONTRADICTS", "NEWS_SECONDARY", EX_B)]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "CONFIRMED_FALSE"
    assert revalidate(direct_vm, sup2()) is False


def test_leader_inconclusive_validator_finds_conclusive_evidence(ta, direct_vm):
    reg(ta); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, llm([src(0, "IRRELEVANT"), src(1, "IRRELEVANT")]))
    set_time(direct_vm, READY_ISO)
    assert ta.resolve_event(1) == "INCONCLUSIVE"
    assert revalidate(direct_vm, sup2()) is False


def test_validator_disagrees_on_entailment_of_the_leaders_own_excerpt(true_result, direct_vm):
    """Expected: classification of both nodes agrees but the validator's entailment of the LEADER's excerpt does not."""
    assert revalidate(direct_vm, sup2(), rels={0: "SUPPORTS", 1: "SUPPORTS"}) is True
    d = json.loads(sup2())
    direct_vm.clear_mocks(); mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"^TASK: SOURCE ANALYSIS", sup2())
    ent = {"items": [{"id": "own-0", "relation": "SUPPORTS"}, {"id": "own-1", "relation": "SUPPORTS"},
                     {"id": "lead-0", "relation": "AMBIGUOUS"}, {"id": "lead-1", "relation": "SUPPORTS"}]}
    direct_vm.mock_llm(r"^TASK: EXCERPT ENTAILMENT", json.dumps(ent))
    assert direct_vm.run_validator() is False


def test_validator_disagrees_on_independence(true_result, direct_vm):
    assert revalidate(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A, same=[1]), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)])) is False


def test_validator_own_analysis_disagrees(true_result, direct_vm):
    assert revalidate(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "AMBIGUOUS")])) is False


def test_validator_says_not_assessable(true_result, direct_vm):
    assert revalidate(direct_vm, llm([src(0), src(1)], assessable=False)) is False


def test_validator_cannot_access_a_source(true_result, direct_vm):
    pages = dict(PAGES_OK); pages[r"news\.example\.org"] = (503, "down")
    assert revalidate(direct_vm, llm([src(0, "SUPPORTS", excerpt=EX_A)]), pages=pages) is False


def test_materially_different_source_version(true_result, direct_vm):
    pages = dict(PAGES_OK); pages[r"gov\.example"] = (200, page("Completely rewritten page with unrelated content here for readers."))
    assert revalidate(direct_vm, sup2(), pages=pages) is False


def test_cosmetic_page_change_is_tolerated(true_result, direct_vm):
    pages = dict(PAGES_OK); pages[r"gov\.example"] = (200, page(TEXT_A) + "<div>Updated 3 minutes ago. Related stories.</div>")
    assert revalidate(direct_vm, sup2(), pages=pages) is True


# --------------------------------- error handling: fail closed ---------------------------------
def test_leader_errors_are_never_accepted(true_result, direct_vm):
    for err in ("[LLM_ERROR] garbage", "[EXPECTED] x", "[EXTERNAL] y", "boom"):
        assert direct_vm.run_validator(leader_error=Exception(err)) is False


def test_validator_llm_failure_fails_closed(true_result, direct_vm):
    direct_vm.clear_mocks(); mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"^TASK: SOURCE ANALYSIS", "[]")
    assert direct_vm.run_validator() is False


def test_unknown_validator_exception_fails_closed(true_result, direct_vm, mod, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(mod, "_analyze", boom)
    assert direct_vm.run_validator() is False


def test_validator_never_writes_state(true_result, ta, direct_vm):
    before = ta.get_event(1)
    direct_vm.run_validator()
    assert ta.get_event(1) == before


def test_naive_validator_would_accept_what_the_real_one_rejects(true_result, direct_vm, mod):
    lies = [
        forge(mod, true_result, lie(lambda fs: fs[0].update(classification=2))),
        forge(mod, true_result, lie(lambda fs: [f.update(classification=3, excerpt="") for f in fs])),
        forge(mod, true_result, lie(lambda fs: fs[0].update(excerpt="the ministry personally confirmed everything about the new law"))),
    ]
    for r in lies:
        assert struct_ok(mod, r) is True            # what a shape-only validator checks
        assert direct_vm.run_validator(leader_result=r) is False


def test_post_consensus_revalidation_blocks_a_bad_accepted_result(ta, direct_vm, mod, monkeypatch):
    import genlayer.gl.vm as glvm
    reg(ta); mock_pages(direct_vm, PAGES_OK); mock_ai(direct_vm, sup2()); set_time(direct_vm, READY_ISO)
    ta.resolve_event(1)
    bad = copy.deepcopy(captured_result(direct_vm)); bad["event_id"] = 99
    reg(ta)
    set_time(direct_vm, iso_plus(READY_ISO, 700))
    monkeypatch.setattr(glvm, "run_nondet_unsafe", lambda *a, **k: bad)
    before = ta.get_event(2)
    with direct_vm.expect_revert("invalid resolution result"):
        ta.resolve_event(2)
    assert ta.get_event(2) == before


# ------------------------------ commitments cover every decision-bearing field ------------------------------
def test_source_commitment_covers_all_stored_decision_fields(mod):
    f = dict(source_id=0, registered_url=URL_A, registrable_domain="gov.example", publisher_group="dom:gov.example",
             title="t" * 5, publication_timestamp=0, update_timestamp=0, retrieval_status=0, source_type=1,
             classification=1, independence_group=0, excerpt="x" * 45, excerpt_fingerprint="ab" * 32)
    base = mod._source_commitment(1, f)
    changes = dict(registered_url=URL_B, registrable_domain="o.example", publisher_group="bbc", title="other",
                   publication_timestamp=5, update_timestamp=5, retrieval_status=4, source_type=3, classification=2,
                   independence_group=1, excerpt="y" * 45, excerpt_fingerprint="cd" * 32)
    for k, v in changes.items():
        assert mod._source_commitment(1, dict(f, **{k: v})) != base, k
    assert mod._source_commitment(2, f) != base and mod._source_commitment(1, f) == base


# ================================ deterministic outcome rules (truth table) ================================
def fnd(cls, group, rs=0):
    return {"classification": cls, "independence_group": group, "retrieval_status": rs}


SUP, CON, AMB, IRR, UNA = 1, 2, 3, 4, 5


@pytest.mark.parametrize("findings,assessable,final,expect", [
    ([], True, False, (3, 1)),
    ([fnd(SUP, 0)], True, False, (3, 1)),
    ([fnd(SUP, 0), fnd(SUP, 1)], True, False, (1, 0)),
    ([fnd(SUP, 0), fnd(SUP, 0)], True, False, (3, 1)),                       # one independent group only
    ([fnd(CON, 0), fnd(CON, 1)], True, False, (2, 0)),
    ([fnd(CON, 0)], True, False, (3, 1)),
    ([fnd(SUP, 0), fnd(CON, 1)], True, False, (3, 3)),
    ([fnd(SUP, 0), fnd(SUP, 1), fnd(CON, 2)], True, False, (3, 3)),
    ([fnd(UNA, 0, 1), fnd(UNA, 1, 1)], True, False, (3, 2)),                 # permanent failures
    ([fnd(SUP, 0), fnd(UNA, 1, 1)], True, False, (3, 1)),
    ([fnd(SUP, 0), fnd(SUP, 1)], False, False, (3, 4)),
    ([fnd(AMB, 0), fnd(IRR, 1)], True, False, (3, 1)),
    ([fnd(UNA, 0, 4), fnd(UNA, 1, 4)], True, False, (0, 5)),                 # temporary: retry, not final
    ([fnd(SUP, 0), fnd(SUP, 1), fnd(UNA, 2, 4)], True, False, (0, 5)),
    ([fnd(SUP, 0), fnd(SUP, 1), fnd(UNA, 2, 6)], True, False, (0, 5)),
    ([fnd(UNA, 0, 3), fnd(UNA, 1, 3)], False, False, (0, 5)),
    ([fnd(UNA, 0, 4), fnd(UNA, 1, 4)], True, True, (3, 2)),                  # final attempt: closes
    ([fnd(SUP, 0), fnd(SUP, 1), fnd(UNA, 2, 4)], True, True, (1, 0)),
])
def test_outcome_truth_table(mod, findings, assessable, final, expect):
    lc, reason, _s, _c = mod._derive_outcome(assessable, findings, final)
    assert (lc, reason) == expect


def test_absence_of_evidence_never_yields_false_or_true(mod):
    for combo in itertools.product([AMB, IRR, UNA], repeat=3):
        fs = [fnd(c, i, 0 if c != UNA else 1) for i, c in enumerate(combo)]
        assert mod._derive_outcome(True, fs, False)[0] == 3


def test_temporary_states_are_exactly_the_documented_set(mod):
    assert set(mod.TEMPORARY_RS) == {2, 3, 4, 6}
    assert 1 not in mod.TEMPORARY_RS and 5 not in mod.TEMPORARY_RS
