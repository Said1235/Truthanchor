import copy
import json
import os
import sys
from datetime import datetime, timezone

CONTRACT = os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "truth_anchor.py")


def iso_ts(iso):
    return int(datetime.fromisoformat(iso).timestamp())


NOW_ISO = "2026-11-13T12:00:00+00:00"          # registration time
READY_ISO = "2026-11-13T12:15:00+00:00"        # 900 s later: past the 600 s minimum resolution delay
NOW_TS = iso_ts(NOW_ISO)
READY_TS = iso_ts(READY_ISO)
EARLIEST_TS = NOW_TS + 600                      # END is far in the past, so the 600 s delay decides
START = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 3, 2, tzinfo=timezone.utc).timestamp())

PROP = "The Ministry of Finance officially published Law 42 in the Official Gazette on 2026-03-01."
DESC = "Context only: tax reform law."
URL_A = "https://www.gov.example/news/law-42"
URL_B = "https://news.example.org/story/law-42"
URL_C = "https://other.example.net/report/law-42"
URLS2 = URL_A + " " + URL_B
URLS3 = URL_A + " " + URL_B + " " + URL_C

TEXT_A = "Official Gazette notice: the Ministry of Finance published Law 42 on 1 March 2026."
TEXT_B = "News report: Law 42 was published by the Ministry of Finance on 1 March 2026, the Gazette confirms."
TEXT_C = "Analysis: the Ministry of Finance did publish Law 42 on 1 March 2026 according to the Gazette."

EX_A = "the Ministry of Finance published Law 42 on 1 March 2026"
EX_B = "Law 42 was published by the Ministry of Finance on 1 March 2026"
EX_C = "the Ministry of Finance did publish Law 42 on 1 March 2026"


def iso_plus(base_iso, seconds):
    from datetime import timedelta
    return (datetime.fromisoformat(base_iso) + timedelta(seconds=seconds)).isoformat()


def set_time(vm, iso):
    """Move the transaction clock. genlayer-test 0.29.2 `warp()` only updates `datetime.now()`; it does NOT
    refresh `gl.message_raw["datetime"]` after deployment, which is the deterministic transaction time the
    contract uses. Update both (tooling limitation, documented in docs/TRUTHANCHOR_DEPLOYMENT_VERIFICATION.md)."""
    vm.warp(iso)
    import genlayer
    genlayer.gl.message_raw["datetime"] = iso


def load_module():
    """The contract module already loaded by direct_deploy (the SDK allows a single Contract class)."""
    return sys.modules["_contract_truth_anchor"]


def page(text):
    return "<html><body><h1>Site</h1><p>" + text + "</p></body></html>"


PAGES_OK = {
    r"gov\.example": (200, page(TEXT_A)),
    r"news\.example\.org": (200, page(TEXT_B)),
    r"other\.example\.net": (200, page(TEXT_C)),
}


def src(sid, cls="SUPPORTS", typ="OFFICIAL_PRIMARY", excerpt="", title="", pub="", upd="", same=None):
    return {
        "source_id": sid, "classification": cls, "source_type": typ, "excerpt": excerpt,
        "title": title, "publication_date": pub, "update_date": upd, "same_origin_as": same or [],
    }


def llm(sources, assessable=True):
    return json.dumps({"proposition_assessable": assessable, "sources": sources})


def ent_json(rels):
    """Entailment mock covering every possible item id (extra ids are ignored by the contract)."""
    items = []
    for i in range(5):
        r = rels.get(i, "AMBIGUOUS")
        items.append({"id": "own-%d" % i, "relation": r})
        items.append({"id": "lead-%d" % i, "relation": r})
    return json.dumps({"items": items})


def mock_ai(vm, analysis, rels=None):
    """Mock both LLM calls. By default the entailment step agrees with the analysis classification."""
    if rels is None:
        d = json.loads(analysis)
        rels = {s["source_id"]: s["classification"] for s in d.get("sources", [])}
    vm.mock_llm(r"^TASK: SOURCE ANALYSIS", analysis)
    vm.mock_llm(r"^TASK: EXCERPT ENTAILMENT", ent_json(rels))


def mock_pages(vm, pages):
    """pages: {url_regex: (status, body)}"""
    for pattern, (status, body) in pages.items():
        vm.mock_web(pattern, {"status": status, "body": body})


def sup2():
    return llm([src(0, "SUPPORTS", "OFFICIAL_PRIMARY", EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)])


def captured_result(vm):
    return copy.deepcopy(vm._captured_validators[-1][0])


def forge(mod, result, mutate, eid=1, final_attempt=False):
    """Make an INTERNALLY CONSISTENT lie: recompute every fingerprint, commitment and the derived outcome."""
    r = copy.deepcopy(result)
    mutate(r)
    fs = r["evidence_findings"]
    for f in fs:
        f["excerpt_fingerprint"] = mod._excerpt_fingerprint(f["excerpt"])
        f["source_commitment"] = mod._source_commitment(r["event_id"], f)
    r["evidence_commitment"] = mod._evidence_commitment(fs)
    lc, reason, s, c = mod._derive_outcome(True, fs, final_attempt)
    r["proposed_outcome"] = mod.RESULT_NAMES[lc]
    r["outcome_reason"] = reason
    r["independent_source_assessment"] = {
        "groups": [f["independence_group"] for f in fs],
        "independent_supporting_groups": s,
        "independent_contradicting_groups": c,
    }
    return r
