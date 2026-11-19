"""Finding A: HTML stripping must be linear and bounded.

All tests exercise the PRODUCTION extraction path: `_page_text_with_work` is the function that
`_fetch_source` calls. Its `work` counter (characters inspected) is asserted against the documented
bound HTML_WORK_FACTOR * len(decoded input) + 64, at 75, 150 and 300 KiB, so the claim does not rest on
wall-clock timing alone (timing is checked only as a coarse supplement)."""
import os
import time

import pytest
from helpers import *
from test_registration import reg

KIB = 1024
SIZES = (75 * KIB, 150 * KIB, 300 * KIB)


def _fit(unit, size):
    return (unit * (size // len(unit) + 1))[:size]


HOSTILE = {
    "lt_only": lambda n: _fit("<", n),
    "gt_only": lambda n: _fit(">", n),
    "open_script": lambda n: _fit("<script ", n),
    "open_style": lambda n: _fit("<style ", n),
    "incomplete_tags": lambda n: _fit("<a ", n),
    "unclosed_comment_chain": lambda n: _fit("<!--", n),
    "unclosed_comment_body": lambda n: "<!--" + "x" * (n - 4),
    "long_quoted_attribute": lambda n: '<a title="' + "x" * (n - 10),
    "quote_and_delimiters": lambda n: _fit("<a b='\"'\"'\">'", n),
    "malformed_nested": lambda n: _fit("<div<div<<>><p<", n),
    "sparse_tags_long_text": lambda n: _fit("lorem ipsum dolor sit amet " * 20 + "<b>", n),
    "large_script_block": lambda n: "<script>" + "x" * (n - 31) + "</script>tail text here",
    "large_style_block": lambda n: "<style>" + "y" * (n - 29) + "</style>tail text here",
    "script_closers_only": lambda n: _fit("</script ", n),
    "mixed_valid_invalid": lambda n: _fit("<p>ok</p><<a<script <!-- &amp ", n),
    "entity_flood": lambda n: _fit("&amp;", n),
    "entity_prefix_flood": lambda n: _fit("&#", n),
    "ampersand_flood": lambda n: _fit("&", n),
    "hex_entity_flood": lambda n: _fit("&#x" + "9" * 9, n),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
@pytest.mark.parametrize("size", SIZES, ids=["75KiB", "150KiB", "300KiB"])
def test_work_is_linear_on_hostile_input(ta, mod, name, size):
    """Expected: work <= HTML_WORK_FACTOR * len + 64 for every hostile shape at every size."""
    body = HOSTILE[name](size).encode("utf-8")
    assert len(body) == size
    text, work = mod._page_text_with_work(body)
    assert work <= mod.HTML_WORK_FACTOR * size + 64, (name, size, work, work / size)
    assert len(text) <= size          # output never grows past the input (no expansion)


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_doubling_input_does_not_quadruple_work(ta, mod, name):
    """Expected: work(300 KiB)/work(150 KiB) stays near 2 (linear), far from 4 (quadratic)."""
    w = {}
    for size in (75 * KIB, 150 * KIB, 300 * KIB):
        w[size] = mod._page_text_with_work(HOSTILE[name](size).encode("utf-8"))[1]
    assert w[150 * KIB] / w[75 * KIB] < 2.6, w
    assert w[300 * KIB] / w[150 * KIB] < 2.6, w


def test_hostile_300kib_completes_quickly_wall_clock_supplement(ta, mod):
    """Supplement only: every hostile 300 KiB shape finishes in seconds (the old regexes needed 33-45 s)."""
    worst = 0.0
    for name in sorted(HOSTILE):
        body = HOSTILE[name](300 * KIB).encode("utf-8")
        t = time.perf_counter()
        mod._page_text_with_work(body)
        worst = max(worst, time.perf_counter() - t)
    assert worst < 8.0, worst


def test_work_bound_is_asserted_against_a_documented_constant(mod):
    """Expected: the bound the tests use is the constant documented in the contract."""
    assert mod.HTML_WORK_FACTOR >= 1 and isinstance(mod.HTML_WORK_FACTOR, int)
    assert mod.MAX_RAW_BYTES >= 300 * KIB and mod.MAX_RAW_BYTES == 512 * KIB


def test_old_vulnerable_path_is_gone(mod):
    """Expected: no regular-expression stripper and no `html` module in the contract source."""
    src = open(CONTRACT).read()
    for needle in ("_SCRIPT_RE", "_TAG_RE", "import html", "html.unescape", ".*?</"):
        assert needle not in src, needle
    assert not hasattr(mod, "_html_to_text")


# ------------------------------------------------------------ correctness
def test_strips_tags_scripts_styles_and_comments(mod):
    text, _ = mod._page_text_with_work(
        b"<html><head><style>p{color:red}</style><SCRIPT type='x'>alert(1)</SCRIPT></head>"
        b"<body>A<!-- hidden -->B <b>bold</b> <scripts>kept</scripts> tail</body></html>"
    )
    assert text == "a b bold kept tail"


def test_entities_are_decoded_once_without_recursion(mod):
    text, _ = mod._page_text_with_work(b"Tom &amp; Jerry &lt;b&gt; &#65;&#x42; &bogus; &#99999999; &#0; &amp;lt; &nbsp;x")
    assert text == "tom & jerry <b> ab &bogus; &#99999999; &#0; &lt; x"


def test_entity_decoded_markup_is_not_reparsed(mod):
    text, _ = mod._page_text_with_work(b"&lt;script&gt;evil()&lt;/script&gt; visible")
    assert text == "<script>evil()</script> visible"


def test_unusual_whitespace_and_hostile_unicode_are_normalised(mod):
    text, _ = mod._page_text_with_work("a\u00a0b\u200bc\n\n\td \u202eevil\u202c \ufeffz".encode("utf-8"))
    assert text == "a bc d evil z"


def test_unterminated_markup_drops_only_the_unterminated_tail(mod):
    assert mod._page_text_with_work(b"keep this text <a href=\"x")[0] == "keep this text"
    assert mod._page_text_with_work(b"keep this <!-- never closed text")[0] == "keep this"
    assert mod._page_text_with_work(b"keep this <script>never closed")[0] == "keep this"


def test_lone_angle_bracket_is_plain_text(mod):
    assert mod._page_text_with_work(b"if a < b and c > d then 1 <2")[0] == "if a < b and c > d then 1 <2"


def test_invalid_utf8_is_replaced_not_fatal(mod):
    text, _ = mod._page_text_with_work(b"caf\xe9 ok \xff\xfe done")
    assert "ok" in text and "done" in text


# --------------------------------------------------- end to end (resolution)
def _resolve_with_pages(ta, vm, pages, analysis=None, rels=None):
    reg(ta)
    mock_pages(vm, pages)
    if analysis is not None:
        mock_ai(vm, analysis, rels)
    set_time(vm, READY_ISO)
    return ta.resolve_event(1)


def test_hostile_300kib_tail_does_not_block_resolution(ta, direct_vm):
    """A real article followed by 300 KiB of hostile markup resolves normally on the retained text."""
    hostile = "<script " * (300 * KIB // 8)
    pages = {
        r"gov\.example": (200, page(TEXT_A) + hostile),
        r"news\.example\.org": (200, page(TEXT_B) + "<a " * (300 * KIB // 3)),
    }
    start = time.perf_counter()
    assert _resolve_with_pages(ta, direct_vm, pages, sup2()) == "CONFIRMED_TRUE"
    assert time.perf_counter() - start < 20
    assert [e["classification"] for e in ta.get_event(1)["evidence"]] == [1, 1]


def test_hostile_page_with_no_extractable_text_is_unavailable_not_evidence(ta, direct_vm):
    pages = {r"gov\.example": (200, "<script " * (300 * KIB // 8)), r"news\.example\.org": (200, "<" * (300 * KIB))}
    assert _resolve_with_pages(ta, direct_vm, pages) == "RETRYABLE"
    ev = ta.get_event(1)
    assert ev["lifecycle_status"] == "OPEN" and ev["attempt_count"] == 1 and ev["evidence"] == []


def test_oversized_raw_body_is_rejected_and_never_evidence(ta, direct_vm, mod):
    big = "x" * (mod.MAX_RAW_BYTES + 1)
    pages = {r"gov\.example": (200, big), r"news\.example\.org": (200, big)}
    assert _resolve_with_pages(ta, direct_vm, pages) == "INCONCLUSIVE"
    ev = ta.get_event(1)
    assert [e["retrieval_status"] for e in ev["evidence"]] == [5, 5]
    assert [e["classification"] for e in ev["evidence"]] == [5, 5] and ev["outcome_reason"] == 2
    assert ev["final_outcome"] != "CONFIRMED_FALSE" and ev["final_outcome"] != "CONFIRMED_TRUE"


def test_oversized_extracted_text_is_rejected_and_never_evidence(ta, direct_vm, mod):
    body = "<p>" + "word " * 9000 + "</p>"          # 45 KB raw, 45 000 extracted chars > limit
    assert len(body) < mod.MAX_RAW_BYTES
    pages = {r"gov\.example": (200, body), r"news\.example\.org": (200, body)}
    assert _resolve_with_pages(ta, direct_vm, pages) == "INCONCLUSIVE"
    assert [e["retrieval_status"] for e in ta.get_event(1)["evidence"]] == [5, 5]


def test_300kib_page_is_not_oversized_at_the_raw_limit(ta, direct_vm, mod):
    pages = {r"gov\.example": (200, page(TEXT_A) + " " * (300 * KIB))}
    mock_pages(direct_vm, pages)
    status, text = mod._fetch_source(URL_A)
    assert status == 0 and "ministry of finance" in text


def test_empty_and_whitespace_pages_are_incomplete_not_evidence(ta, direct_vm, mod):
    mock_pages(direct_vm, {r"gov\.example": (200, ""), r"news\.example\.org": (200, "<p>   </p>")})
    assert mod._fetch_source(URL_A) == (2, "")
    assert mod._fetch_source(URL_B) == (2, "")


def test_raw_size_limit_is_enforced_independently_of_the_extracted_text_size(ta, direct_vm, mod):
    """Expected: a body above MAX_RAW_BYTES is OVERSIZED even when almost all of it is stripped markup, so a
    huge page can never be reduced to a small excerpt-bearing text and become evidence."""
    body = page(TEXT_A) + "<script>" + "x" * (mod.MAX_RAW_BYTES + 10) + "</script>"
    assert len(body.encode()) > mod.MAX_RAW_BYTES
    mock_pages(direct_vm, {r"gov\.example": (200, body)})
    assert mod._fetch_source(URL_A) == (5, "")


def test_page_exactly_at_the_raw_limit_is_still_processed(ta, direct_vm, mod):
    filler = "<!--" + "x" * (mod.MAX_RAW_BYTES - len(page(TEXT_A).encode()) - 7) + "-->"
    body = page(TEXT_A) + filler
    assert len(body.encode()) == mod.MAX_RAW_BYTES
    mock_pages(direct_vm, {r"gov\.example": (200, body)})
    status, text = mod._fetch_source(URL_A)
    assert status == 0 and "ministry of finance" in text
