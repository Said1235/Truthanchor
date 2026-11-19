"""Findings B.2-B.5: excerpts must be meaningful evidence; corroboration is counted over independent
publishers and unique content, never over raw URLs, hosts or excerpts."""
import json
import time

import pytest
from helpers import *
from test_registration import reg


def resolve(ta, vm, urls=URLS2, pages=None, analysis=None, rels=None):
    reg(ta, source_urls=urls)
    mock_pages(vm, pages or PAGES_OK)
    mock_ai(vm, analysis or sup2(), rels)
    set_time(vm, READY_ISO)
    return ta.resolve_event(1)


def ev(ta):
    return ta.get_event(1)["evidence"]


# ======================= B.2 meaningful, relevant excerpts =======================
NAV = "home | news | sports | weather | contact us | privacy policy | terms of use | about us"
COOKIE = "we use cookies to improve your experience by continuing to browse you accept our cookie policy"
SITE = "this website provides daily news coverage and analysis for readers around the world"
UNRELATED = "the local football club announced a new striker after a long and difficult transfer window"
KEYWORDS = "ministry of finance staff said the official gazette canteen reopened after law 42 renovation work"


def page_with(extra):
    return {r"gov\.example": (200, page(TEXT_A + " " + extra)), r"news\.example\.org": (200, page(TEXT_B + " " + extra))}


@pytest.mark.parametrize("label,excerpt", [
    ("trivial", "the"),
    ("one_word_long_token", "Ministry-of-Finance-published-Law-42-on-1-March-2026-in-the-Gazette"),
    ("short_with_anchors", "Law 42 published by the Ministry"),
    ("navigation", NAV),
    ("cookie_notice", COOKIE),
    ("site_description", SITE),
    ("unrelated_paragraph", UNRELATED),
    ("five_words_only", "Ministry published Law 42 officially today"),
])
def test_B2_trivial_or_unanchored_excerpt_is_not_corroboration(ta, direct_vm, label, excerpt):
    """Expected: excerpts that fail the minimum evidence policy count as neither support nor contradiction."""
    extra = " ".join([NAV, COOKIE, SITE, UNRELATED])
    analysis = llm([src(0, "SUPPORTS", excerpt=excerpt), src(1, "SUPPORTS", "NEWS_SECONDARY", excerpt)])
    assert resolve(ta, direct_vm, pages=page_with(extra), analysis=analysis) == "INCONCLUSIVE"
    e = ta.get_event(1)
    assert e["outcome_reason"] == 1 and [x["classification"] for x in e["evidence"]] == [3, 3]
    assert all(x["excerpt"] == "" for x in e["evidence"])          # a rejected excerpt is not stored as evidence


def test_B2_keyword_overlap_alone_is_not_proof_of_relevance(ta, direct_vm):
    """Expected: an excerpt full of proposition keywords but irrelevant to it is rejected by the entailment step."""
    analysis = llm([src(0, "SUPPORTS", excerpt=KEYWORDS), src(1, "SUPPORTS", "NEWS_SECONDARY", KEYWORDS)])
    out = resolve(ta, direct_vm, pages=page_with(KEYWORDS), analysis=analysis, rels={0: "IRRELEVANT", 1: "IRRELEVANT"})
    assert out == "INCONCLUSIVE"
    assert [x["classification"] for x in ev(ta)] == [4, 4] and ta.get_event(1)["outcome_reason"] == 1


def test_B2_keyword_overlap_passes_the_lexical_filter_so_the_semantic_step_is_the_real_gate(ta, mod):
    """Expected: the lexical filter is necessary, not sufficient (documented policy)."""
    text = mod._norm(KEYWORDS)
    assert mod._excerpt_ok(text, text, mod._anchors(mod._norm(PROP)))
    assert not mod._excerpt_ok(mod._norm(NAV), mod._norm(NAV), mod._anchors(mod._norm(PROP)))


@pytest.mark.parametrize("rel,expected_cls", [("AMBIGUOUS", 3), ("IRRELEVANT", 4), ("CONTRADICTS", 3)])
def test_B2_entailment_that_does_not_confirm_the_claimed_relation_downgrades_it(ta, direct_vm, rel, expected_cls):
    """Expected: a SUPPORTS claim needs an independent SUPPORTS entailment on the excerpt in its context."""
    out = resolve(ta, direct_vm, rels={0: rel, 1: rel})
    assert out == "INCONCLUSIVE" and [x["classification"] for x in ev(ta)] == [expected_cls, expected_cls]


def test_B2_context_reversal_is_caught_by_the_context_aware_step(ta, direct_vm):
    """Expected: a phrase whose context negates it must not corroborate (the context window is what the judge sees)."""
    neg = "RUMOUR: it is claimed that the Ministry of Finance published Law 42 on 1 March 2026 but officials deny this."
    pages = {r"gov\.example": (200, page(neg)), r"news\.example\.org": (200, page(neg + " More."))}
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_A)])
    out = resolve(ta, direct_vm, pages=pages, analysis=analysis, rels={0: "CONTRADICTS", 1: "AMBIGUOUS"})
    assert out == "INCONCLUSIVE"


def test_B2_entailment_receives_the_surrounding_context(ta, direct_vm, mod, monkeypatch):
    """Expected: the judge sees the excerpt AND up to CONTEXT_CHARS of page text on each side."""
    import genlayer.gl.nondet as nd
    seen = []
    orig = nd.exec_prompt

    def spy(prompt, *a, **k):
        seen.append(prompt)
        return orig(prompt, *a, **k)

    monkeypatch.setattr(nd, "exec_prompt", spy)
    resolve(ta, direct_vm)
    ent = [p for p in seen if p.startswith("TASK: EXCERPT ENTAILMENT")][0]
    items = json.loads(ent.split("\nDATA: ")[1].split("\nREMINDER")[0])["items"]
    assert items and all(len(i["context"]) > len(i["excerpt"]) for i in items)
    assert all(i["excerpt"] in i["context"] for i in items)


def test_B2_excerpt_must_exist_in_the_page_text(ta, direct_vm):
    """Expected: a quotation that is not in the fetched, normalised page is rejected (never upgraded)."""
    fake = "the minister personally confirmed that law 42 was published on 1 march 2026 in the gazette"
    analysis = llm([src(0, "SUPPORTS", excerpt=fake), src(1, "SUPPORTS", "NEWS_SECONDARY", fake)])
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE"
    assert [x["classification"] for x in ev(ta)] == [3, 3]


def test_B2_excerpt_from_another_source_is_rejected(ta, direct_vm):
    """Expected: evidence is bound to ITS source: B's quotation attributed to A is not in A's text."""
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_B), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)])
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE"
    cls = [x["classification"] for x in ev(ta)]
    assert cls[0] == 3 and cls[1] == 1


def test_B2_stored_excerpt_reproduces_exactly_from_the_normalised_page(ta, direct_vm, mod):
    """Expected: exact quotation/source correspondence. Offsets are not stored (page chrome shifts them between
    independent fetches); the stored excerpt is the canonical normalised string and must occur verbatim."""
    assert resolve(ta, direct_vm) == "CONFIRMED_TRUE"
    for i, e in enumerate(ev(ta)):
        text = mod._page_text_with_work(PAGES_OK[[r"gov\.example", r"news\.example\.org"][i]][1].encode())[0]
        assert e["excerpt"] != "" and e["excerpt"] in text and mod._norm(e["excerpt"]) == e["excerpt"]
        assert e["excerpt_fingerprint"] == mod._excerpt_fingerprint(e["excerpt"]) and len(e["excerpt_fingerprint"]) == 64
        assert set(e) >= {"registrable_domain", "publisher_group", "excerpt_fingerprint", "independence_group"}
        assert not any("offset" in k or k in ("start", "end") for k in e)


def test_B2_minimum_policy_constants_are_documented_and_enforced(ta, mod):
    assert (mod.MIN_EXCERPT_CHARS, mod.MIN_EXCERPT_WORDS, mod.MAX_EXCERPT) == (40, 6, 300)
    t = mod._norm(EX_A)
    anchors = mod._anchors(mod._norm(PROP))
    assert mod._excerpt_ok(t, t, anchors)
    assert not mod._excerpt_ok(t[:39], t, anchors) and not mod._excerpt_ok(t, "other page text entirely", anchors)


def test_B2_contradictory_evidence_stays_visible_and_blocks_a_verdict(ta, direct_vm):
    """Expected: independent sources that conflict are preserved; no arbitrary or leader-only decision."""
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "CONTRADICTS", "NEWS_SECONDARY", EX_B)])
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE"
    e = ta.get_event(1)
    assert e["outcome_reason"] == 3 and [x["classification"] for x in e["evidence"]] == [1, 2]
    assert all(x["excerpt"] for x in e["evidence"])


def test_B2_missing_evidence_is_never_a_false_conclusion(ta, direct_vm):
    """Expected: no usable support or contradiction -> INCONCLUSIVE, never CONFIRMED_FALSE."""
    analysis = llm([src(0, "IRRELEVANT"), src(1, "IRRELEVANT")])
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE"
    assert ta.get_event(1)["final_outcome"] == "INCONCLUSIVE" and ta.get_event(1)["outcome_reason"] == 1


def test_B2_confirmed_false_requires_real_independent_contradiction(ta, direct_vm):
    analysis = llm([src(0, "CONTRADICTS", excerpt=EX_A), src(1, "CONTRADICTS", "NEWS_SECONDARY", EX_B)])
    assert resolve(ta, direct_vm, analysis=analysis) == "CONFIRMED_FALSE"


def test_B2_proposition_not_assessable_is_inconclusive(ta, direct_vm):
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)], assessable=False)
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE" and ta.get_event(1)["outcome_reason"] == 4


# ================ B.3/B.4 duplicate content and trusted source identity ================
def two_hosts(url_a, url_b, text_a, text_b, rx_a, rx_b):
    return url_a + " " + url_b, {rx_a: (200, text_a), rx_b: (200, text_b)}


ARTICLE = (
    "The Ministry of Finance published Law 42 on 1 March 2026 in the Official Gazette. "
    + " ".join("clause%d detail%d" % (k, k * 7) for k in range(90))
)


def test_B4_identical_content_on_different_domains_is_one_source(ta, direct_vm):
    """Expected: byte-identical normalised pages on different hosts count once."""
    urls, pages = two_hosts(URL_A, URL_B, page(ARTICLE), page(ARTICLE), r"gov\.example", r"news\.example\.org")
    out = resolve(ta, direct_vm, urls, pages, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_A)]))
    assert out == "INCONCLUSIVE"
    e = ta.get_event(1)
    assert [x["independence_group"] for x in e["evidence"]] == [0, 0] and e["outcome_reason"] == 1
    assert len(e["evidence"]) == 2                                   # the duplicate is kept as provenance


def test_B4_near_identical_content_with_different_site_chrome_is_one_source(ta, direct_vm):
    """Expected: the same article wrapped in different navigation/footers is still a copy."""
    a = page("HOME NEWS WORLD " + ARTICLE)
    b = page(ARTICLE + " Related stories subscribe footer privacy terms")
    urls, pages = two_hosts(URL_A, URL_B, a, b, r"gov\.example", r"news\.example\.org")
    out = resolve(ta, direct_vm, urls, pages, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_A)]))
    assert out == "INCONCLUSIVE" and [x["independence_group"] for x in ev(ta)] == [0, 0]


def test_B4_same_decision_excerpt_through_different_pages_counts_once(ta, direct_vm):
    """Expected: the same relevant excerpt reached via alternate URLs/mirrors is counted once."""
    a = page("Section one. " + EX_A + ". " + " ".join("aaa%d" % k for k in range(30)))
    b = page("Other layout entirely. " + " ".join("bbb%d" % k for k in range(30)) + " " + EX_A + ". Tail.")
    urls, pages = two_hosts(URL_A, URL_B, a, b, r"gov\.example", r"news\.example\.org")
    out = resolve(ta, direct_vm, urls, pages, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_A)]))
    assert out == "INCONCLUSIVE" and [x["independence_group"] for x in ev(ta)] == [0, 0]


def test_B3_two_hostnames_of_one_registered_domain_are_one_publisher(ta, direct_vm):
    """Expected: different hostnames alone are not proof of independence."""
    urls, pages = two_hosts("https://news.example.org/a/law-42", "https://www.example.org/b/law-42",
                            page(TEXT_A), page(TEXT_B), r"news\.example\.org", r"^https://www\.example\.org")
    out = resolve(ta, direct_vm, urls, pages)
    assert out == "INCONCLUSIVE"
    e = ev(ta)
    assert e[0]["registrable_domain"] == e[1]["registrable_domain"] == "example.org"
    assert [x["independence_group"] for x in e] == [0, 0]


def test_B3_subdomains_of_the_same_domain_are_one_publisher(ta, direct_vm):
    urls, pages = two_hosts("https://a.example.org/x/law-42", "https://b.example.org/y/law-42",
                            page(TEXT_A), page(TEXT_B), r"a\.example\.org", r"b\.example\.org")
    assert resolve(ta, direct_vm, urls, pages) == "INCONCLUSIVE"


def test_B3_registered_publisher_group_spans_different_domains(ta, direct_vm):
    """Expected: bbc.com and bbc.co.uk belong to one registered owner group."""
    urls, pages = two_hosts("https://www.bbc.com/news/law-42", "https://www.bbc.co.uk/news/law-42",
                            page(TEXT_A), page(TEXT_B), r"bbc\.com", r"bbc\.co\.uk")
    assert resolve(ta, direct_vm, urls, pages) == "INCONCLUSIVE"
    e = ev(ta)
    assert [x["publisher_group"] for x in e] == ["bbc", "bbc"] and e[0]["registrable_domain"] != e[1]["registrable_domain"]


def test_B3_shared_hosting_tenants_are_not_one_publisher(ta, direct_vm):
    """Expected: alice.github.io and bob.github.io are different owners (suffix list), so they may corroborate."""
    urls, pages = two_hosts("https://alice.github.io/p/law-42", "https://bob.github.io/p/law-42",
                            page(TEXT_A), page(TEXT_B), r"alice\.github\.io", r"bob\.github\.io")
    assert resolve(ta, direct_vm, urls, pages) == "CONFIRMED_TRUE"
    assert [x["independence_group"] for x in ev(ta)] == [0, 1]


def test_B3_multi_label_public_suffix_keeps_different_owners_apart(ta, direct_vm):
    urls, pages = two_hosts("https://www.alpha.co.uk/n/law-42", "https://www.beta.co.uk/n/law-42",
                            page(TEXT_A), page(TEXT_B), r"alpha\.co\.uk", r"beta\.co\.uk")
    assert resolve(ta, direct_vm, urls, pages) == "CONFIRMED_TRUE"
    assert [x["registrable_domain"] for x in ev(ta)] == ["alpha.co.uk", "beta.co.uk"]


def test_B3_model_flagged_shared_origin_can_only_merge(ta, direct_vm):
    """Expected: merge-only. The model can lower, never raise, the independent count."""
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_A, same=[1]), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B)])
    assert resolve(ta, direct_vm, analysis=analysis) == "INCONCLUSIVE"
    assert [x["independence_group"] for x in ev(ta)] == [0, 0]


def test_B5_corroboration_counts_independent_groups_not_urls(ta, direct_vm):
    """Expected: 3 URLs, 2 of them one publisher -> 2 independent groups -> still a valid TRUE."""
    urls = "https://news.example.org/a/law-42 https://www.example.org/b/law-42 " + URL_C
    pages = {r"news\.example\.org": (200, page(TEXT_A)), r"^https://www\.example\.org": (200, page(TEXT_B)),
             r"other\.example\.net": (200, page(TEXT_C))}
    analysis = llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B), src(2, "SUPPORTS", "OTHER", EX_C)])
    assert resolve(ta, direct_vm, urls, pages, analysis) == "CONFIRMED_TRUE"
    e = ta.get_event(1)
    assert [x["independence_group"] for x in e["evidence"]] == [0, 0, 2]


def test_B5_valid_independent_corroboration_after_eligibility_is_finalised(ta, direct_vm):
    assert resolve(ta, direct_vm, URLS3, PAGES_OK, llm([
        src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_B), src(2, "SUPPORTS", "OTHER", EX_C)])) == "CONFIRMED_TRUE"
    e = ta.get_event(1)
    assert e["lifecycle_status"] == "RESOLVED_TRUE" and e["resolution_timestamp"] == READY_TS and len(e["evidence_commitment"]) == 64


def test_B5_a_duplicate_does_not_rescue_a_single_real_source(ta, direct_vm):
    """Expected: one real source plus its mirror is still one source."""
    mirror = page(TEXT_A)
    urls, pages = two_hosts(URL_A, URL_B, page(TEXT_A), mirror, r"gov\.example", r"news\.example\.org")
    assert resolve(ta, direct_vm, urls, pages, llm([src(0, "SUPPORTS", excerpt=EX_A), src(1, "SUPPORTS", "NEWS_SECONDARY", EX_A)])) == "INCONCLUSIVE"


def test_B4_duplicate_detection_work_is_bounded_with_five_large_sources(ta, direct_vm, mod):
    """Expected: at most 10 pairwise comparisons over bounded shingle sets; no quadratic content comparison."""
    words = " ".join("w%d" % (k % 997) for k in range(3600))
    texts = [mod._norm(words + " v%d" % i) for i in range(5)]
    t = time.perf_counter()
    groups = mod._groups(["a", "b", "c", "d", "e"], texts, [""] * 5, [])
    assert time.perf_counter() - t < 6 and groups == [0, 0, 0, 0, 0]     # near-copies of one text


def test_B4_unrelated_pages_are_not_merged(ta, mod):
    t1 = mod._norm(" ".join("alpha%d" % k for k in range(200)))
    t2 = mod._norm(" ".join("beta%d" % k for k in range(200)))
    assert mod._groups(["a", "b"], [t1, t2], ["", ""], []) == [0, 1]
