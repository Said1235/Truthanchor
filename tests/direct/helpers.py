import copy
import importlib.util
import json
import os
from datetime import datetime, timezone

CONTRACT = os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "truth_anchor.py")

NOW_ISO = "2026-11-13T12:00:00+00:00"
NOW_TS = int(datetime(2026, 11, 13, 12, tzinfo=timezone.utc).timestamp())
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
EX_C = "did publish Law 42 on 1 March 2026"


def load_module():
    """The contract module already loaded by direct_deploy (the SDK allows a single Contract class)."""
    import sys
    return sys.modules["_contract_truth_anchor"]


def src(sid, cls="SUPPORTS", typ="OFFICIAL_PRIMARY", excerpt="", title="", pub="", upd="", same=None):
    return {
        "source_id": sid, "classification": cls, "source_type": typ, "excerpt": excerpt,
        "title": title, "publication_date": pub, "update_date": upd, "same_origin_as": same or [],
    }


def llm(sources, assessable=True):
    return json.dumps({"proposition_assessable": assessable, "sources": sources})


def mock_pages(vm, pages):
    """pages: {url_regex: (status, body)}"""
    for pattern, (status, body) in pages.items():
        vm.mock_web(pattern, {"status": status, "body": body})


PAGES_OK = {
    r"gov\.example": (200, "<html><body><h1>Gazette</h1><p>" + TEXT_A + "</p></body></html>"),
    r"news\.example\.org": (200, "<html><body><p>" + TEXT_B + "</p></body></html>"),
    r"other\.example\.net": (200, "<html><body><p>" + TEXT_C + "</p></body></html>"),
}


def sup2():
    return llm([src(0, "SUPPORTS", "OFFICIAL_PRIMARY", EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)])


def captured_result(vm):
    return copy.deepcopy(vm._captured_validators[-1][0])


def forge(mod, result, mutate, eid=1):
    """Make an INTERNALLY CONSISTENT lie: recompute every commitment and the derived outcome."""
    r = copy.deepcopy(result)
    mutate(r)
    fs = r["evidence_findings"]
    for f in fs:
        f["source_commitment"] = mod._source_commitment(r["event_id"], f)
    r["evidence_commitment"] = mod._evidence_commitment(fs)
    lc, reason, s, c = mod._derive_outcome(True, fs)
    r["proposed_outcome"] = mod.OUTCOME_NAMES[lc]
    r["outcome_reason"] = reason
    r["independent_source_assessment"] = {
        "groups": [f["independence_group"] for f in fs],
        "independent_supporting_groups": s,
        "independent_contradicting_groups": c,
    }
    return r
