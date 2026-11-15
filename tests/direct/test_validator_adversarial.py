"""A lying leader must be rejected. Every forged result here is INTERNALLY CONSISTENT
(valid structure, valid commitments, derived outcome matches its own findings), so only
the validator's independent re-derivation can catch it. A naive validator that checks
'valid JSON + same outcome' would accept them (see test_naive_validator_would_accept)."""
import copy
import pytest
from helpers import *
from test_registration import reg


@pytest.fixture
def resolved(ta, direct_vm, mod):
    reg(ta)
    mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"PROPOSITION", sup2())
    assert ta.resolve_event(1) == "CONFIRMED_TRUE"
    return captured_result(direct_vm)


def validate(direct_vm, result):
    return direct_vm.run_validator(leader_result=result)


def test_honest_leader_accepted(resolved, direct_vm):
    assert direct_vm.run_validator() is True
    assert validate(direct_vm, resolved) is True


def forged(mod, resolved, fn):
    return forge(mod, resolved, fn)


def test_lie_classification_flipped(resolved, direct_vm, mod):
    r = forged(mod, resolved, lambda x: x["evidence_findings"][0].update(classification=2))
    assert mod._check_structure(r, 1, PROP, URLS2.split()) is True     # well-formed lie
    assert validate(direct_vm, r) is False


def test_lazy_leader_cannot_force_inconclusive(resolved, direct_vm, mod):
    def lazy(x):
        for f in x["evidence_findings"]:
            f.update(classification=4, excerpt="")
    r = forged(mod, resolved, lazy)
    assert r["proposed_outcome"] == "INCONCLUSIVE"
    assert mod._check_structure(r, 1, PROP, URLS2.split()) is True
    assert validate(direct_vm, r) is False


def test_lie_fabricated_excerpt(resolved, direct_vm, mod):
    r = forged(mod, resolved, lambda x: x["evidence_findings"][0].update(excerpt="the Ministry confirmed everything"))
    assert mod._check_structure(r, 1, PROP, URLS2.split()) is True
    assert validate(direct_vm, r) is False


def test_lie_fabricated_title(resolved, direct_vm, mod):
    r = forged(mod, resolved, lambda x: x["evidence_findings"][1].update(title="Totally invented headline"))
    assert validate(direct_vm, r) is False


def test_lie_retrieval_status(resolved, direct_vm, mod):
    r = forged(mod, resolved, lambda x: x["evidence_findings"][1].update(retrieval_status=1, classification=5, excerpt=""))
    assert mod._check_structure(r, 1, PROP, URLS2.split()) is True
    assert validate(direct_vm, r) is False


def test_lie_source_type_and_dates(resolved, direct_vm, mod):
    assert validate(direct_vm, forged(mod, resolved, lambda x: x["evidence_findings"][0].update(source_type=3))) is False
    assert validate(direct_vm, forged(mod, resolved, lambda x: x["evidence_findings"][0].update(publication_timestamp=START))) is False


def test_lie_independence_groups(resolved, direct_vm, mod):
    r = forged(mod, resolved, lambda x: x["evidence_findings"][1].update(independence_group=0))
    assert r["proposed_outcome"] == "INCONCLUSIVE"
    assert validate(direct_vm, r) is False


@pytest.mark.parametrize("name,mut", [
    ("event_id", lambda r: r.update(event_id=2)),
    ("proposition", lambda r: r.update(proposition="A different proposition that was never registered.")),
    ("schema_version", lambda r: r.update(schema_version=2)),
    ("criteria_version", lambda r: r.update(criteria_version=9)),
    ("substituted_url", lambda r: r["evidence_findings"][0].update(registered_url="https://evil.example.org/fake-page")),
    ("missing_source", lambda r: r["evidence_findings"].pop()),
    ("extra_source", lambda r: r["evidence_findings"].append(copy.deepcopy(r["evidence_findings"][0]))),
    ("wrong_publisher_host", lambda r: r["evidence_findings"][0].update(publisher_host="trusted.example.gov")),
    ("stale_commitment", lambda r: r["evidence_findings"][0].update(source_commitment="0" * 64)),
    ("stale_evidence_commitment", lambda r: r.update(evidence_commitment="f" * 64)),
    ("outcome_lie_only", lambda r: r.update(proposed_outcome="CONFIRMED_FALSE")),
    ("reason_lie_only", lambda r: r.update(outcome_reason=3)),
    ("extra_key", lambda r: r.update(concise_explanation="trust me")),
    ("missing_key", lambda r: r.pop("evidence_commitment")),
    ("string_instead_of_int", lambda r: r["evidence_findings"][0].update(classification="1")),
    ("bool_instead_of_int", lambda r: r["evidence_findings"][0].update(source_id=True)),
    ("oversized_excerpt", lambda r: r["evidence_findings"][0].update(excerpt="x" * 301)),
    ("not_a_dict", lambda r: None),
])
def test_tampered_results_rejected(resolved, direct_vm, name, mut):
    r = copy.deepcopy(resolved)
    mut(r)
    if name == "not_a_dict":
        r = ["not", "a", "dict"]
    assert validate(direct_vm, r) is False, name


def test_forced_ambiguous_on_conclusive_evidence(resolved, direct_vm, mod):
    r = copy.deepcopy(resolved)
    r["proposed_outcome"] = "INCONCLUSIVE"; r["outcome_reason"] = 4
    assert mod._check_structure(r, 1, PROP, URLS2.split()) is True
    assert validate(direct_vm, r) is False


def test_page_changed_between_leader_and_validator(resolved, direct_vm):
    direct_vm.clear_mocks()
    mock_pages(direct_vm, {**PAGES_OK, r"gov\.example": (200, "<p>This page was edited and no longer mentions the law.</p>")})
    direct_vm.mock_llm(r"PROPOSITION", sup2())
    assert direct_vm.run_validator() is False


def test_source_down_for_validator(resolved, direct_vm):
    direct_vm.clear_mocks()
    mock_pages(direct_vm, {**PAGES_OK, r"news\.example\.org": (500, "err")})
    direct_vm.mock_llm(r"PROPOSITION", llm([src(0, "SUPPORTS", excerpt=EX_A)]))
    assert direct_vm.run_validator() is False


def test_validator_own_llm_disagrees(resolved, direct_vm):
    direct_vm.clear_mocks()
    mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"PROPOSITION", llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "CONTEXT_ONLY")]))
    assert direct_vm.run_validator() is False


def test_validator_llm_says_not_assessable(resolved, direct_vm):
    direct_vm.clear_mocks()
    mock_pages(direct_vm, PAGES_OK)
    direct_vm.mock_llm(r"PROPOSITION", llm([src(0), src(1)], assessable=False))
    assert direct_vm.run_validator() is False


def test_leader_error_is_not_accepted_as_success(resolved, direct_vm):
    # leader reported a UserError; validator re-runs, the analysis succeeds -> must not agree
    assert direct_vm.run_validator(leader_error=Exception("[LLM_ERROR] garbage")) is False


def test_llm_error_is_raised_by_analysis_so_validator_reproduces_it(ta, direct_vm, mod):
    """When the LLM really fails, the validator's own analysis raises the same [LLM_ERROR]
    (Direct Mode does not capture a validator for a leader that failed before consensus)."""
    import genlayer.gl.vm as v
    mock_pages(direct_vm, PAGES_OK); direct_vm.mock_llm(r"PROPOSITION", "[]")
    with pytest.raises(v.UserError) as ei:
        mod._analyze(1, PROP, DESC, START, END, URLS2.split(), NOW_TS)
    assert ei.value.message.startswith("[LLM_ERROR]")


def test_compare_user_errors_policy(mod):
    import genlayer.gl.vm as v
    ll = v.UserError("[LLM_ERROR] a")
    assert mod._compare_user_errors(ll, v.UserError("[LLM_ERROR] a")) is False     # forces leader rotation
    assert mod._compare_user_errors(v.UserError("[EXPECTED] x"), v.UserError("[EXPECTED] x")) is True
    assert mod._compare_user_errors(v.UserError("[EXPECTED] x"), v.UserError("[EXPECTED] y")) is False


def test_naive_validator_would_accept(resolved, direct_vm, mod):
    """Contrast: a validator that only checks 'is a Return with valid shape' accepts the lies."""
    lies = [
        forged(mod, resolved, lambda x: x["evidence_findings"][0].update(classification=2)),
        forged(mod, resolved, lambda x: [f.update(classification=4, excerpt="") for f in x["evidence_findings"]]),
        forged(mod, resolved, lambda x: x["evidence_findings"][0].update(excerpt="the Ministry confirmed everything")),
    ]
    for lie in lies:
        assert mod._check_structure(lie, 1, PROP, URLS2.split()) is True      # naive check passes...
        assert validate(direct_vm, lie) is False                                # ...the real validator does not


def test_post_consensus_revalidation_blocks_bad_result(ta, direct_vm, mod, monkeypatch):
    """Defense in depth: even if consensus were bypassed, the contract re-validates before persisting."""
    import genlayer.gl.vm as glvm
    reg(ta); mock_pages(direct_vm, PAGES_OK); direct_vm.mock_llm(r"PROPOSITION", sup2())
    ta.resolve_event(1)
    good = captured_result(direct_vm)
    bad = copy.deepcopy(good); bad["event_id"] = 99
    assert mod._check_structure(bad, 1, PROP, URLS2.split()) is False
    reg(ta)   # event 2 stays open
    monkeypatch.setattr(glvm, "run_nondet", lambda *a, **k: bad)
    with direct_vm.expect_revert("invalid resolution result"):
        ta.resolve_event(2)
    assert ta.get_event_status(2) == "OPEN"
