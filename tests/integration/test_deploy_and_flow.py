"""Integration tests (need a running GenLayer Studio/network). NOT EXECUTED in the build
environment: there is no Studio there. Run with:  TA_RUN_INTEGRATION=1 gltest tests/integration -v -s

Resolution on real validators needs live LLMs and live pages; this file covers the
zero-argument deployment requirement and the registration/read flow, plus a resolution
smoke test against two public pages you choose via env vars.
"""
import os
import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

pytestmark = pytest.mark.skipif(
    os.environ.get("TA_RUN_INTEGRATION") != "1",
    reason="integration tests need Studio/network; set TA_RUN_INTEGRATION=1",
)

PROP = "The Ministry of Finance officially published Law 42 in the Official Gazette on 2026-03-01."


def test_deploy_with_empty_args_and_initial_state():
    factory = get_contract_factory("TruthAnchor", contract_file_path="contracts/truth_anchor.py")
    contract = factory.deploy(args=[])          # zero constructor arguments
    assert contract.get_event_count(args=[]).call() == 0
    assert contract.list_event_ids(args=[0, 20]).call() == []
    assert contract.get_limits(args=[]).call()["min_sources"] == 2


def test_register_and_read_event():
    factory = get_contract_factory("TruthAnchor", contract_file_path="contracts/truth_anchor.py")
    contract = factory.deploy(args=[])
    receipt = contract.register_event(
        args=[PROP, "context", 1772323200, 1772409600,
              "https://www.example.org/a-page https://www.example.net/b-page", 0]
    ).transact()
    assert tx_execution_succeeded(receipt)      # ACCEPTED/FINALIZED alone do not prove success
    ev = contract.get_event(args=[1]).call()
    assert ev["proposition"] == PROP and ev["lifecycle_status"] == "OPEN"


@pytest.mark.skipif(not (os.environ.get("TA_URL_1") and os.environ.get("TA_URL_2")), reason="set TA_URL_1/TA_URL_2")
def test_resolve_smoke_on_real_validators():
    factory = get_contract_factory("TruthAnchor", contract_file_path="contracts/truth_anchor.py")
    contract = factory.deploy(args=[])
    prop = os.environ.get("TA_PROPOSITION", PROP)
    reg = contract.register_event(
        args=[prop, "", int(os.environ.get("TA_START", "1772323200")), int(os.environ.get("TA_END", "1772409600")),
              os.environ["TA_URL_1"] + " " + os.environ["TA_URL_2"], 0]).transact()
    assert tx_execution_succeeded(reg)
    res = contract.resolve_event(args=[1]).transact()
    assert tx_execution_succeeded(res)
    assert contract.get_event_status(args=[1]).call() in ("RESOLVED_TRUE", "RESOLVED_FALSE", "INCONCLUSIVE")
