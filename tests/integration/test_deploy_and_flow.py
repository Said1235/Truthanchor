"""Integration tests (need a running GenLayer Studio/network). NOT EXECUTED in the build environment: there is no
Studio there. Run with:   TA_RUN_INTEGRATION=1 gltest tests/integration -v -s

What they cover: deployment with an EMPTY argument list, the initial state, registration and reads, and the
eligibility rule on a real network. A real resolution needs real time to pass (the minimum resolution delay is
600 s after registration) and live pages/LLMs, so it is opt-in:

    TA_URL_1=https://... TA_URL_2=https://... TA_WAIT_FOR_ELIGIBILITY=1 TA_RUN_INTEGRATION=1 gltest tests/integration -v -s
"""
import os
import time

import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

pytestmark = pytest.mark.skipif(
    os.environ.get("TA_RUN_INTEGRATION") != "1",
    reason="integration tests need Studio/network; set TA_RUN_INTEGRATION=1",
)

PROP = "The Ministry of Finance officially published Law 42 in the Official Gazette on 2026-03-01."
CONTRACT_FILE = "contracts/truth_anchor.py"


def deploy():
    factory = get_contract_factory("TruthAnchor", contract_file_path=CONTRACT_FILE)
    return factory.deploy(args=[])          # zero constructor arguments


def register(contract, urls="https://www.example.org/a-page https://www.example.net/b-page"):
    return contract.register_event(args=[PROP, "context", 1772323200, 1772409600, urls, 0]).transact()


def test_deploy_with_empty_args_and_initial_state():
    contract = deploy()
    assert contract.get_event_count(args=[]).call() == 0
    assert contract.list_event_ids(args=[0, 20]).call() == []
    limits = contract.get_limits(args=[]).call()
    assert limits["min_sources"] == 2 and limits["criteria_version"] == 2
    assert limits["max_raw_bytes_per_source"] >= 300 * 1024


def test_register_and_read_event_with_eligibility_metadata():
    contract = deploy()
    receipt = register(contract)
    assert tx_execution_succeeded(receipt)      # ACCEPTED/FINALIZED alone do not prove success
    ev = contract.get_event(args=[1]).call()
    assert ev["proposition"] == PROP and ev["lifecycle_status"] == "OPEN"
    assert ev["earliest_resolution_timestamp"] >= ev["registration_timestamp"] + 600
    assert ev["attempt_count"] == 0 and ev["resolution_timestamp"] == 0


def test_immediate_resolution_is_rejected_and_leaves_the_event_open():
    contract = deploy()
    assert tx_execution_succeeded(register(contract))
    receipt = contract.resolve_event(args=[1]).transact()
    assert not tx_execution_succeeded(receipt)  # "event is not yet eligible for resolution"
    ev = contract.get_event(args=[1]).call()
    assert ev["lifecycle_status"] == "OPEN" and ev["resolution_timestamp"] == 0 and ev["attempt_count"] == 0


@pytest.mark.skipif(
    not (os.environ.get("TA_URL_1") and os.environ.get("TA_URL_2") and os.environ.get("TA_WAIT_FOR_ELIGIBILITY") == "1"),
    reason="set TA_URL_1, TA_URL_2 and TA_WAIT_FOR_ELIGIBILITY=1 (the test sleeps past the 600 s delay)",
)
def test_resolve_after_eligibility_on_real_validators():
    contract = deploy()
    assert tx_execution_succeeded(register(contract, os.environ["TA_URL_1"] + " " + os.environ["TA_URL_2"]))
    time.sleep(int(os.environ.get("TA_WAIT_SECONDS", "660")))
    assert tx_execution_succeeded(contract.resolve_event(args=[1]).transact())
    status = contract.get_event_status(args=[1]).call()
    # Either finalised, or still OPEN with a recorded retryable attempt if a page was temporarily unavailable.
    assert status in ("RESOLVED_TRUE", "RESOLVED_FALSE", "INCONCLUSIVE", "OPEN")
    if status == "OPEN":
        assert contract.get_event(args=[1]).call()["attempt_count"] >= 1
