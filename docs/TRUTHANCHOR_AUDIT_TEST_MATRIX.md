# TruthAnchor - Audit Test Matrix

Generated from the real pytest JUnit output of the full direct suite (`tests/direct`: 177 tests, including the 60 audit tests listed below).

- Contract under test: `contracts/truth_anchor.py`, SHA-256 `6fdf243441b1fe025fa04485cf122e0df67221f3c717531bf9f87e3126ae3095` (byte-identical before and after the audit).
- Environment: GenVM v0.2.16 bundle (runner `py-genlayer:1jb45aa8...`), `genlayer-test` 0.29.2, Python 3.12.3, `cloudpickle` 3.1.2 (pickling check active), `strict_mocks` enabled.

## Legend

- **PASS (executed)**: the safe/expected behaviour was observed.
- **DEFECT CONFIRMED (executed; safe behaviour NOT met)**: the test asserts the safe behaviour and is marked `xfail(strict=True)`; it fails today. Each maps to a finding in `TRUTHANCHOR_AUDIT_REPORT.md`. When the finding is fixed the test flips to XPASS and strict mode fails the suite until the marker is removed.
- **NOT EXECUTED**: the scenario could not be run in this environment (reason given).
- Direct Mode runs on the host CPython with mocked web and LLM. It does **not** prove real multi-validator consensus, runner-level resource limits, or Studio schema loading.

## A. Deployment

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| A01 | zero argument constructor schema | generated ABI has a constructor with no parameters. | Yes | PASS (executed) |  |
| A02 | initial state and post deploy registration | empty registry after deploy; registration works with no further setup. | Yes | PASS (executed) |  |

## B. Event identity and history

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| B01 | same wallet multiple events | distinct monotonically increasing ids, each retrievable by exact id. | Yes | PASS (executed) |  |
| B02 | two callers register | each event records its own submitter; no cross-assignment. | Yes | PASS (executed) |  |
| B03 | resolution by other caller keeps event binding | a third party resolving event 1 changes only event 1; event 2 untouched. | Yes | PASS (executed) |  |
| B04 | no latest result confusion | registering event 2 after event 1 does not change what resolve(1) stores. | Yes | PASS (executed) |  |
| B05 | failed registration does not consume an id | an invalid registration reverts without incrementing the counter. | Yes | PASS (executed) |  |
| B06 | history is preserved after reverification | the old result stays retrievable and unchanged; the new record links to it. | Yes | PASS (executed) |  |
| B07 | nonexistent and invalid ids | unknown ids revert with [EXPECTED]; ids beyond u64 do not crash. | Yes | PASS (executed) |  |

## C. Leader-validator contradictions

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| C01 | leader true validator finds contradiction | REJECT. Leader TRUE; validator sees a CONTRADICTS source. | Yes | PASS (executed) |  |
| C02 | leader false validator finds support | REJECT. Leader FALSE; validator sees SUPPORTS on both. | Yes | PASS (executed) |  |
| C03 | leader inconclusive validator finds conclusive | REJECT. A terminal INCONCLUSIVE must be reproduced, not rubber-stamped. | Yes | PASS (executed) |  |
| C04 | leader omits a material source | REJECT. Finding list shorter than the registered source list. | Yes | PASS (executed) |  |
| C05 | leader fabricates quotation | REJECT. Consistent forgery whose excerpt is not in the page. | Yes | PASS (executed) |  |
| C06 | leader attributes evidence to wrong source | REJECT. Excerpt of source B attributed to source A. | Yes | PASS (executed) |  |
| C07 | leader changes proposition | REJECT. | Yes | PASS (executed) |  |
| C08 | leader changes event interval | REJECT. The interval is not a leader field; adding one is a schema violation. | Yes | PASS (executed) |  |
| C09 | leader omits contradictory finding | REJECT. Validator finds a contradiction the leader did not report. | Yes | PASS (executed) |  |
| C10 | leader wrong source commitment | REJECT. | Yes | PASS (executed) |  |
| C11 | leader malformed structure | REJECT for each malformed shape. | Yes | PASS (executed) |  |
| C12 | valid outcome but materially false findings | REJECT. Same CONFIRMED_TRUE outcome, but source 1 is really CONTEXT_ONLY. | Yes | PASS (executed) |  |
| C13 | validator cannot access a source | REJECT (never silently treated as agreement). | Yes | PASS (executed) |  |
| C14 | materially different source versions | REJECT. | Yes | PASS (executed) |  |
| C15 | validators disagree on source independence | REJECT. Validator judges the two sources to be copies of one publication. | Yes | PASS (executed) |  |

## D. Source integrity

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| D01 | two independent sources confirm | CONFIRMED_TRUE. | Yes | PASS (executed) |  |
| D02 | two syndicated copies are not independent | INCONCLUSIVE (reason 1) when the LLM flags a shared origin. | Yes | PASS (executed) |  |
| D03 | duplicate urls rejected | reverts. | Yes | PASS (executed) |  |
| D04 | identical content on different hosts is not independent | INCONCLUSIVE. Two hosts serving identical text must not count as two sources. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-06 |
| D05 | primary and secondary types are recorded | source_type stored per source (OFFICIAL_PRIMARY=1, NEWS_SECONDARY=2). | Yes | PASS (executed) |  |
| D06 | unavailable source is not falsity | never CONFIRMED_FALSE. | Yes | PASS (executed) |  |
| D07 | redirect status is treated as unavailable | 3xx is not 2xx -> UNAVAILABLE. Whether GenVM follows redirects is UNVERIFIED. | Yes | PASS (executed) |  |
| D08 | contradictory sources are inconclusive | INCONCLUSIVE reason 3. | Yes | PASS (executed) |  |
| D09 | source without publication date | timestamp 0 (unknown), outcome unaffected. | Yes | PASS (executed) |  |
| D10 | misleading publication date is not stored | a date that does not appear in the retrieved page is stored as 0. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-08 |

## E. Prompt injection

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| E01 | page injection stays inside source block and is neutralised | injected page text cannot reproduce the real delimiter (normalisation lower-cases it) and carries the untrusted-data warning. | Yes | PASS (executed) |  |
| E02 | injected page cannot force outcome without a real quotation | a model that obeys the injection still cannot get a conclusive result: excerpt must exist in the page. | Yes | PASS (executed) |  |
| E03 | injection attempting fabricated evidence is degraded | fabricated quotation degrades the finding to INSUFFICIENT. | Yes | PASS (executed) |  |
| E04 | user description cannot inject prompt structure | user-controlled text cannot reproduce prompt delimiters or add instruction lines. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-03 |
| E05 | user proposition cannot inject prompt structure | the proposition cannot smuggle extra instruction lines into the prompt. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-03 |
| E06 | url cannot spoof delimiters | a URL cannot reproduce the source delimiter. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-03 |

## F. Storage and data types

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| F01 | bool is not accepted as integer | reverts (bool is a distinct type). | Yes | PASS (executed) |  |
| F02 | u256 boundary parent id | max u256 parent id -> 'parent event not found'; max+1 -> out of range. | Yes | PASS (executed) |  |
| F03 | timestamp ordering and maximum | start>end rejected; end=2**64-1 rejected as future; 2**64 rejected as out of range. | Yes | PASS (executed) |  |
| F04 | empty collections and nested records round trip | empty evidence before resolution; N nested SourceEvidence records after. | Yes | PASS (executed) |  |
| F05 | oversized strings rejected | reverts at every bound. | Yes | PASS (executed) |  |
| F06 | no address parameters exist | no public method takes an Address; the only Address field is the sender-derived submitter. | Yes | PASS (executed) |  |

## G. Failure handling

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| G01 | malformed llm json reverts and leaves event open | [LLM_ERROR]; state untouched. | Yes | PASS (executed) |  |
| G02 | retry after failure succeeds without duplicates | the retry resolves the same event id; evidence appears exactly once. | Yes | PASS (executed) |  |
| G03 | web exception is unavailable not falsity | an exception from the web layer yields FETCH_ERROR/UNAVAILABLE, never CONFIRMED_FALSE. | Yes | PASS (executed) |  |
| G04 | no state is written before the nondeterministic block completes | if run_nondet raises (consensus not reached), the event is exactly as before. | Yes | PASS (executed) |  |
| G05 | leader error never accepted as success | REJECT for a leader error when the validator can succeed. | Yes | PASS (executed) |  |
| G06 | vm error leader result | REJECT / handled by compare_vm_errors. | No | NOT EXECUTED | Direct Mode run_validator() can only wrap leader errors as UserError; a gl.vm.VMError leader result cannot be synthesised |
| G07 | real multi validator consensus | disagreement -> leader rotation -> state unchanged if undetermined. | No | NOT EXECUTED | needs a running Studio/network with real validators (multi-validator consensus, appeals, rotation) |

## Confirmed-defect proofs (xfail means the defect is present)

| ID | Scenario | Expected result | Executed | Actual result | Finding / note |
|---|---|---|---|---|---|
| FND02 | trivial excerpt is not accepted as evidence | INCONCLUSIVE. An excerpt of a few characters cannot constitute supporting evidence. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-02 |
| FND02b | irrelevant excerpt is not accepted | the excerpt must support the proposition; a real but unrelated sentence must not. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-02 |
| FND01 | html stripping is linear time | doubling a hostile page size at most ~doubles processing time (ratio < 3). | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-01 |
| FND04 | transient outage does not finalize the event | when every source is unreachable the resolution reverts and the event stays OPEN. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-04 |
| FND05 | third party can finalize inconclusive immediately | Documented design risk F-05 (passes): any caller may resolve right after registration; INCONCLUSIVE is terminal. | Yes | PASS (executed) | F-05 (documented design risk; behaviour observed) |
| FND07 | commitment covers decision bearing fields | changing independence_group, source_type or title changes the source commitment. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-07 |
| FND09 | typecheck is clean | `genvm-lint typecheck` exits 0. | Yes | DEFECT CONFIRMED (executed; safe behaviour NOT met) | F-09 |

## Pre-existing suite (executed, all PASS)

| File | Tests | Covers |
|---|---|---|
| `test_registration.py` | 32 | zero-arg deploy and initial state; monotonic ids; submitter; 24 parametrised rejections (proposition, description, interval, future end, 2-5 sources, duplicate after normalisation, http scheme, credentials, IP hosts, localhost, internal hosts, IPv6, port, URL length, non-ASCII, oversized list, unknown parent); boundaries; views do not mutate |
| `test_resolution.py` | 28 | TRUE / FALSE / INCONCLUSIVE with every reason; unavailable sources never FALSE; same host and syndicated copies; fabricated excerpt degraded; title and date handling; HTML and quote normalisation; 9 malformed LLM outputs leave the event OPEN; double resolution; interleaved events; re-verification |
| `test_validator_adversarial.py` | 36 | internally consistent forged results (classification, excerpt, title, retrieval status, source type, dates, groups, lazy INCONCLUSIVE); 18 tampering cases; page changed; source down for the validator; validator LLM disagrees; leader errors; `compare_user_errors`; naive-validator contrast; post-consensus re-validation |
| `test_helpers.py` | 32 | URL validation and normalisation; counter guard; outcome truth table; absence of evidence never FALSE; merge-only groups; commitments; date bounds; schema has 0 constructor parameters |

Mutation check: replacing `_validator_agrees` with a naive validator (structure check only) makes 13 of the 36 `test_validator_adversarial.py` tests fail; the genuine validator passes all 36.

## Totals for the audit tests in this file

PASS 47 | DEFECT CONFIRMED 11 | NOT EXECUTED 2 | FAIL 0

Full-suite totals: 175 passed, 2 skipped, 11 xfailed (confirmed defects), 0 failed.
