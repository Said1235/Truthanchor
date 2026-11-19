# TruthAnchor - Security Remediation Report

| | |
|---|---|
| **Authoritative contract** | `contracts/truth_anchor.py` (1 291 lines), criteria v2 |
| **SHA-256** | `50fd280f9444069f4b19017da0f2482629c9a1f853e027c45bd5d341c67fc157` |
| **Reviewed baseline** | tag `v0.1.0-audited-baseline` (commit `a11ce54`), contract SHA-256 `6fdf243441b1fe025fa04485cf122e0df67221f3c717531bf9f87e3126ae3095` |
| **Target** | SDK generation A: `# v0.2.16` + `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (GenVM v0.2.16) |
| **Public interface** | Unchanged: constructor `__init__(self)` with no arguments and the same 7 method signatures (`abi.json` is byte-identical to the baseline's) |
| **Live deployment** | **None performed.** Nothing was broadcast to any network. |

The review rejected the submission for three reasons. This report records, for each, the root cause in the previous
implementation, the exact change, why it addresses the underlying problem, and what is still not solved. It is based on the
repository's real code, the SDK source of the target runner, and executed tests; every number below was measured.

## 0. Summary of what changed

| Area | Before (baseline) | After (this remediation) |
|---|---|---|
| HTML stripping | two backtracking regexes, quadratic; `html` module; body truncated at 300 000 bytes and the prefix used as evidence | single-pass scanner with a monotone cursor and a work counter; no regex, no `html`; oversized pages rejected, never evidence |
| Prompt | proposition, description and URLs concatenated into the text | fixed contract-owned policy + ONE JSON data line; description and URLs not in the prompt |
| Excerpts | any substring of the page counted | sentence-sized, anchored, present in the page and judged **in context** by an independent entailment step on both leader and validators |
| Independence | exact host + model hint | registered publisher groups, registrable domains, identical/near-identical content, identical excerpts, model links (merge-only) |
| Resolution timing | any caller, any time | not before `max(event_end + 3600 s, registration + 600 s)` by the transaction timestamp, for everyone |
| Temporary failures | became a terminal `INCONCLUSIVE` | the event stays `OPEN`, the attempt is recorded, it can be retried; documented closure condition |
| Validators | `run_nondet` | `run_nondet_unsafe` with explicit fail-closed handling of every leader and validator error |
| Static checks | `typecheck` exit 1 | `typecheck` clean |
| Deployment artifacts | none | `deploy/` manifest, constructor arguments, guarded script, consistency verifier (18 checks) |
| Stale copy | `variants/runner-kzybg95x/` (a second, vulnerable, deployable contract) | removed from the working tree (kept in git history and in the baseline tag) |

Final evidence: 381 direct tests pass (0 failed, 0 skipped); `genvm-lint` check/lint/validate/typecheck/schema all clean;
21 of 21 security mutants are killed; deployment verification 18 PASS. Studio deployment, integration tests, real LLM behaviour,
real multi-validator consensus and execution on the GenVM WASM runner are **not run** (section 6).

---

## 1. Finding A - Quadratic, unbounded HTML stripping

### Root cause (baseline `contracts/truth_anchor.py`)

- `_SCRIPT_RE = <(script|style)\b.*?</\1\s*>` with `DOTALL` (L80): for every `<script` that is never closed, the lazy `.*?` runs to the end of the
  input before failing, then the engine retries from the next position. `k` unterminated openers over an input of length `n` cost `O(k*n)`.
- `_TAG_RE = <[^>]*>` (L81): for every `<` without a later `>`, `[^>]*` runs to the end. Same `O(k*n)` shape.
- `_html_to_text` (L179-185) applied both to up to `MAX_BODY_BYTES = 300000` bytes, i.e. **below** 300 KiB (307 200).
- `_fetch_source` sliced the body to `MAX_BODY_BYTES` and processed the prefix, so a truncated page could become evidence.
- Reproduced on the baseline at the real size (300 KiB = 307 200 bytes, same patterns and flags): `<script ` flood **33.5 s**; `<` flood **45.2 s**.

### Change

Files and functions: `contracts/truth_anchor.py` - `_strip_markup` (L307), `_entity_value` (L374), `_decode_entities` (L398),
`_page_text_with_work` (L433), `_fetch_source` (L447), `_norm` (L297, extended); constants `MAX_RAW_BYTES = 512 KiB` (L90),
`MAX_TEXT_CHARS = 20 000` (L91), `HTML_WORK_FACTOR = 5` (L93). **Removed:** `_SCRIPT_RE`, `_TAG_RE`, `_html_to_text`,
`import html`, `MAX_BODY_BYTES` (a test asserts none of them exist).

- `_strip_markup` is a single pass. The cursor `i` only moves forward. Every `str.find` either succeeds, after which the cursor jumps past the match
  (that range is never scanned again), or fails, after which the rest is dropped and the loop ends. Each iteration advances at least one
  character. Output is collected in a list and joined once. Tag names are matched on a length-preserving ASCII lower-cased copy (one pass).
- `_decode_entities` is a second single pass; a name scan stops at the first character that cannot belong to an entity name and never looks past 12
  characters. Decoded output is never rescanned, so there is no recursive or compounding expansion; numeric entities are range- and digit-checked.
  Entity-decoded markup (`&lt;script&gt;`) is not re-parsed.
- No recursion, no regex, no third-party parser. The standard-library `html`, `re`, `json` and `datetime` modules do exist in the GenVM CPython
  runtime (verified by listing the stdlib in runtime `cpython:1bk9g3zg...` of the v0.2.16 bundle), but the new parser needs none of the first two.
- Bounds (project-defined, not protocol limits): raw body at most 512 KiB (**above** the 300 KiB hostile test); extracted text at most 20 000 characters
  (5 pages x 20 000 characters bounds the prompt to about 25 000 tokens); at most 5 pages per resolution. A page over either limit is classified
  `OVERSIZED` (a permanent state) and is never evidence for either outcome. No tag/attribute-count limits are needed because the work bound does not depend on them.

### Proof

- **Work counter, not only timing.** `_page_text_with_work` is the production extraction function called by `_fetch_source`; it returns the number of
  characters inspected. Tests assert `work <= 5 * len(input) + 64` for **19 hostile shapes at 75, 150 and 300 KiB** (angle-bracket floods, repeated incomplete
  tags, unclosed comments, a 300 KiB quoted attribute, quote/delimiter mixes, malformed nesting, sparse tags in long text, 300 KiB script/style blocks,
  entity and ampersand floods). The measured ratio work/size is **identical at all three sizes** for every shape (2.0 to 4.0, worst case `lt_only` 4.0), which is the
  signature of linear growth; a second test asserts that doubling the input never more than 2.6x the work.
- Wall clock (supplement only, host CPython): the slowest of the 19 shapes at 300 KiB takes **0.197 s**, against 33.5-45.2 s for the baseline.
- End to end: a real article followed by 300 KiB of hostile markup still resolves on the retained text; a hostile page with no extractable text is retryable, not evidence.
- Oversized: a raw body above the limit that strips to a small text is `OVERSIZED` (this case was added after the mutation check showed the text-size limit
  masked the raw-size limit); a body exactly at the limit is processed; a 300 KiB page is not oversized.
- Mutations M01 (rescanning scanner), M14 (raw limit removed), M19 (text limit removed) are killed.

### Residual risk

- Measurements are on host CPython. GenVM runs CPython on WASM, likely slower by a constant factor; the algorithm is linear, but the real CPU/memory metering and timeouts of the runner are undocumented in the pages read and **unverified**.
- A pure-Python loop still runs once per `<` that is plain text and once per `&`; at the 512 KiB cap this is bounded (about 0.2 s here for 300 KiB).
- `web.get` behaviour on redirects, timeouts and maximum size is not documented in the pages read; 3xx is classified permanent-unavailable.

---

## 2. Finding B - Prompt injection, trivial excerpts, and fake corroboration

### B.1 Caller-controlled prompt text

**Root cause.** `_build_prompt` (baseline L326-353) concatenated the stored proposition (L336), the free-form description (L337) and each URL (L331) into the
instruction text, with line-based delimiters (`<<<SOURCE ...>>>`) as the only boundary. A caller could add lines, spoof delimiters or append instructions.
The official *Prompt Injection* guidance (restrict inputs; build prompts inside the contract) was not followed.

**Change.** `_POLICY`, `_ANALYSIS_SPEC`, `_ENTAIL_SPEC` (constants), `_build_analysis_prompt` (L674), `_build_entail_prompt` (L686), `_canon`.
- The task and evaluation policy are fixed contract constants. Everything untrusted (the proposition and every page text) is carried in **one line of JSON**
  (`DATA: <json>`, `ensure_ascii=True`, compact separators), so quotes, newlines, delimiters, JSON-shaped instructions, chat-template tokens and Unicode controls are escaped by the
  serializer, not by hand-made quoting. The prompt is pure ASCII.
- `description` is stored but **never enters the evaluation**; URLs are not in the prompt (sources are referenced by numeric id only); no public method accepts prompt, policy or criteria text.
- Page text is normalised before use (`_norm`): bidi controls, zero-width characters, BOM and control characters are removed.
- Security is also enforced **outside the model**: model output is parsed strictly (`_parse_llm`, `_entail`: closed vocabularies, exact id sets, `[LLM_ERROR]` on any violation) and
  never executed (extra keys are ignored); a conclusive finding needs a verbatim quotation present in the page; and the validators re-derive everything independently.

**Proof.** 35 tests: the trusted text is identical for any caller input and no line can be added (8 hostile payloads, both prompts); every hostile string round-trips verbatim inside
the JSON line; page injections remain data; a model that is *fooled* (mock) and quotes the injection obtains no conclusive result; hostile/malformed model JSON leaves state unchanged.
Mutation M13 (proposition appended outside the data) is killed.

**Residual risk.** A real LLM may still be influenced by text inside the data; no prompt defence is complete (OWASP). If both the leader's and the validators' models are
fooled the same way, consensus cannot detect it; the deterministic anchors (verbatim quotation, minimum evidence policy, independent groups) limit but do not remove this. Mocks cannot show real model behaviour: **NOT RUN**.

### B.2 Trivial or irrelevant excerpts

**Root cause.** The only guard was `ex in text` (baseline L435-437, validator L561-564): `"the"` or a real but unrelated sentence counted as supporting evidence
(baseline tests FND02/FND02b).

**Change.** `_anchors` (L474), `_excerpt_ok` (L482), `_context` (L494), `_entail` (L737), `_analyze` (L760), `_check_finding` (L899), `_validator_agrees` (L971); relation vocabulary `SUPPORTS / CONTRADICTS / AMBIGUOUS / IRRELEVANT` (+ `UNAVAILABLE`).
- **Necessary filters (deterministic):** 40-300 characters, at least 6 words, at least 2 salient tokens of the proposition (tokens of 5+ characters or numbers of 2+ digits, falling back to 3+), and present in that source's normalised text. These are *necessary, not sufficient*: they remove navigation text, cookie notices, site descriptions and unrelated paragraphs; they are explicitly not proof of relevance and keyword overlap alone never counts.
- **Semantic gate:** a second model call judges each decision-bearing excerpt **in its context** (up to 400 characters of page text on each side) as supports/contradicts/ambiguous/irrelevant, so a phrase whose context reverses its meaning is not classified by the phrase alone. The final classification is the analysis classification only if the entailment agrees; otherwise it is downgraded.
- **Validators judge the leader's actual excerpt** on their own copy of the page (`lead-<id>` items) and must obtain the same relation; they also re-run the full analysis and must obtain the same classification, type, group and dates. Contradictory findings stay visible and block a verdict (rule R3).
- The stored excerpt is the canonical normalised string that was verified; `excerpt_fingerprint = Keccak256(excerpt)` is recomputed by the contract. **Offsets are not stored**: independent fetches of the same page shift positions (ads, timestamps), so offset equality would reject valid results; exact quotation presence in the validator's own text is verified instead.

**Proof.** 18 mandatory cases in the matrix (S05) plus structure-gate tests that reject forged short/unnormalised/ambiguous-with-excerpt findings. Mutations M02, M03, M04, M05, M15 are killed.

**Residual risk.** The entailment step is an LLM judgement; two models can agree wrongly. The thresholds are language-agnostic heuristics: scripts written without spaces (e.g. Chinese or Japanese) cannot reach 6 "words", so such excerpts are rejected conservatively (result `INCONCLUSIVE`, never a false conclusion).

### B.3/B.4/B.5 Source independence and copied content

**Root cause.** `_groups` (baseline L279-305) merged only sources with the exact same host plus the model's `same_origin_as` hint. Byte-identical pages on different hosts, subdomains, different domains of one owner and the same excerpt reached through mirrors all counted as independent.

**Change.** `_registrable` (L280), `_SUFFIXES` (L114), `PUBLISHER_GROUPS` (L129), `_publisher_group` (L290), `_shingles` (L508), `_near_duplicate` (L520), `_groups` (L527); storage fields `registrable_domain`, `publisher_group`, `excerpt_fingerprint`, `independence_group`.
- **Trusted identity, not caller-supplied.** Identities are derived only from the registered URLs and from tables compiled into the contract: a *partial* multi-label/shared-hosting suffix list (one label below `co.uk`, `github.io`, ... is one owner) and a static registry of publisher groups (e.g. `bbc.com` + `bbc.co.uk`). It is **not** the naive "last two labels" rule: shared-hosting tenants stay independent and the list only ever *merges*. `resolve_event` takes only an event id.
- **Deterministic duplicate detection** before counting: identical normalised page text; near-identical text by bounded word-5-gram containment (at least 80 % of the smaller page, at least 20 shingles; deterministic FNV hashing, not Python's randomised `hash`); identical decision-bearing excerpts; model-flagged shared origin. At most 5 sources, so at most 10 bounded comparisons, over at most 3 000 words each. A duplicate stays in the evidence as provenance but does not raise the independent count.
- **Validators derive it themselves.** They fetch the pages, normalise, compute groups and require the same partition as the leader; no fingerprint or group from the leader is trusted. Page-level fingerprints are deliberately *not* stored or compared: dynamic page chrome changes them between independent fetches, which would reject valid results; the committed, verified fields are the groups and the excerpt fingerprint.
- Corroboration is counted over independent groups of sources that are fetched OK, have a policy-compliant verbatim excerpt, a matching entailment, and no unresolved contradiction (`_derive_outcome`, L623).

**Proof.** S06 (6 cases), S07 (19 cases), S11. Mutations M06, M07, M08 are killed.

**Residual risk.** The suffix list and publisher registry are partial seed lists; extending them needs a new deployment (the contract has no owner by design). Mirrors that rewrite most of the text, paraphrased copies, or unrelated-looking domains of one owner are not detected. Merging errs towards fewer independent groups, so some legitimate corroboration may yield `INCONCLUSIVE`. The submitter chooses the sources; two sites the submitter controls that publish different text still count as two sources.

---

## 3. Finding C - Temporary failures and premature calls finalised events irreversibly

### Root cause (baseline)

- `resolve_event` (L683-743) had no eligibility rule: any caller could finalise right after registration.
- `_fetch_source` (L309-323) mapped every failure (5xx, 429, timeout, any exception, 404) to `UNAVAILABLE`; `_derive_outcome` rule R4 turned "no admissible source and some unavailable" into a **terminal** `INCONCLUSIVE` (baseline tests FND04 and FND05 demonstrate both).

### Change

`EventRecord` gains `earliest_resolution_timestamp`, `attempt_count`, `last_attempt_timestamp`, `last_attempt_reason`; `register_event` (L1048) stores the earliest time; `resolve_event` (L1114); `_fetch_source`; `_derive_outcome(assessable, findings, final_attempt)` (L623); `_analyze`; constants `SETTLEMENT_DELAY_SECONDS`, `MIN_RESOLUTION_DELAY_SECONDS`, `RETRY_CLOSURE_ATTEMPTS`, `RETRY_CLOSURE_WINDOW_SECONDS`.

- **Eligibility.** `earliest = max(event_end + 3600 s, registration + 600 s)`, stored at registration. `resolve_event` reverts with `[EXPECTED] event is not yet eligible for resolution` before the transaction time (`gl.message_raw["datetime"]`) reaches it, for **every** caller, with no state change. No LLM, source publication time, caller-provided time or host clock is involved (a test asserts the source contains none of `datetime.now`, `time.time`, `utcnow`...).
- **Retry classes** (stored as `retrieval_status`): `OK 0`; **temporary** (retryable): `HTTP_TEMPORARY 4` (5xx, 408, 425, 429), `NOT_FOUND 6` (404: possibly not yet published), `EMPTY 2` (2xx with an empty/unreadable body: incomplete response), `FETCH_ERROR 3` (any exception from the web layer, including unknown ones: fail closed); **permanent** (not retryable): `HTTP_PERMANENT 1` (3xx, 401, 403, 410, 451 and other 4xx), `OVERSIZED 5`.
- **Rule.** While any source is temporary and the attempt is not final, the consensus result is `RETRYABLE` (`outcome_reason 5`): no outcome, no finalization timestamp, no commitments, no evidence; only `attempt_count`, `last_attempt_timestamp` and `last_attempt_reason` are recorded, the event stays `OPEN` and eligible. This also holds when other sources are healthy (an unavailable source might contradict) and when only one source is available. The LLM is not called for a retryable attempt (cheaper).
- **Closure condition (the only way temporary failures can end an event).** After `RETRY_CLOSURE_ATTEMPTS = 3` recorded attempts **and** `RETRY_CLOSURE_WINDOW_SECONDS = 24 h` past the eligibility time, temporary states count as unavailable: the event can close `INCONCLUSIVE` (reason 2), or conclusively from the remaining evidence. This is the deliberate, documented closure condition for `INCONCLUSIVE`; it is never used for timeouts, 5xx, malformed LLM output or early requests before that point.
- **Terminal states.** `INCONCLUSIVE` is terminal only for: proposition not assessable (4); contradictory independent evidence (3); insufficient independent evidence with every source definitively processed (1); permanent-unavailable sources (2); and the closure condition (2). `RESOLVED_FALSE` needs at least two independent groups of verified contradiction and no support; absence of evidence never produces it (exhaustively tested). A terminal event cannot be resolved again, by anyone; a re-investigation is a new linked event.
- **Consensus and state.** `gl.vm.run_nondet_unsafe` is used (the official page recommends it for custom logic). The validator is fail-closed: a leader result that is not `gl.vm.Return` (`UserError`, `VMError`, anything else) is rejected, forcing rotation; `.calldata` is read only after the `Return` check and the deterministic structure gate; any exception raised by the validator's own analysis (temporary failure, malformed LLM output, unknown error) rejects; a leader `RETRYABLE` must be reproduced by the validator's own fetch; a leader factual result is rejected if the validator's own fetch is temporarily failing. Storage is written only on the deterministic path after the accepted result passes `_check_structure` again, and the event's `OPEN` state is re-checked.

### Conformance with the official *Error Handling* page

Read in full during this remediation (https://docs.genlayer.com/developers/intelligent-contracts/features/error-handling). It lists four VM result types (`Return`, `VMError`,
`UserError`, `InternalError`) and, for `run_nondet_unsafe`, an error-classification pattern for validators: deterministic errors should match exactly; transient errors
(network, server) are expected on both sides; LLM errors should **disagree**, "which forces a rotation to a new leader".

| Official pattern | TruthAnchor |
|---|---|
| Check the result type before using the leader value | `isinstance(leaders_res, gl.vm.Return)` first; `.calldata` only after it and after the deterministic structure gate |
| LLM/malformed output: disagree so a new leader is chosen | `[LLM_ERROR]` raised by the leader makes the validator return `False`; a validator-side LLM error also returns `False` |
| Transient network/server failures: both sides hitting one is expected | These are **not raised as errors**. They are encoded in the result as `RETRYABLE` with per-source retrieval statuses, and the validator must reproduce them from its own fetch (C26); a validator that hits a temporary failure when the leader did not rejects (C25) |
| Deterministic business-logic errors should match | All deterministic validation (eligibility, state, inputs) runs **before** the non-deterministic block, so the leader raises no deterministic error inside it |
| Unknown errors | Fail closed: unknown leader results and any exception in the validator return `False` |

Two differences, reported rather than hidden: (1) the page's example validator re-runs the leader function and agrees when both raise the same business error; this contract
never raises one inside the block, so it unconditionally disagrees with a leader that errored. (2) The page's example catches `gl.UserError`, but the installed SDK of
runner `1jb45aa8...` exports only `gl.vm.UserError` (`hasattr(gl, "UserError")` is false there); the contract uses `gl.vm.UserError`.

### Proof

46 lifecycle tests: 11 temporary response classes (all five 5xx variants, 429, 408, 425, 404, empty/blank 200) leave the event open with exact state assertions and remain retryable; timeouts and unknown exceptions; a single good source plus a 5xx; one flaky source among enough evidence; retry after recovery; closure needs **both** conditions (and at closure the remaining evidence decides); permanent failures never become a negative fact; immediate third-party resolution at 0 s and 599 s is rejected with the state unchanged, allowed exactly at the earliest timestamp, and a recent event end postpones eligibility; repeated resolution after a terminal result never overwrites it; validator-side checks (C25, C26). Mutations M09, M10, M12, M17, M18, M20, M21 are killed.

### Residual risk

- A source that is permanently flaky keeps the event `OPEN` until the closure condition (at least 24 h and 3 attempts). Registrants should choose reliable sources.
- Anyone can record retry attempts (a recorded attempt is cheap); attempts alone cannot close an event, the 24 h window is also required.
- A permanent 4xx such as `403` produced by bot-blocking finalises `INCONCLUSIVE` immediately; it is never a negative fact, and a re-investigation can follow.
- A page that returns `200` with a placeholder before the real content is published is not detected.
- The delays (600 s, 3600 s, 3 attempts, 24 h) are project-defined constants, not protocol parameters, and are not configurable per event.

---

## 4. Other changes made on the way

- `SCHEMA_VERSION` and `CRITERIA_VERSION` are 2. Storage layout changed (new fields); there is no deployed instance, so no migration was needed.
- Commitments now cover every decision-bearing stored field (`title`, `source_type`, `independence_group`, `publisher_group`, `registrable_domain`, `excerpt`, `excerpt_fingerprint`...) - baseline audit finding F-07.
- `_err` is annotated `typing.NoReturn`; `genvm-lint typecheck` now exits 0 (baseline audit F-09).
- Dead code removed (baseline audit F-10); `run_nondet` replaced by `run_nondet_unsafe` with explicit fail-closed handling (baseline audit F-11).
- Duplicate deployable source removed: `variants/runner-kzybg95x/` (a vulnerable, unaudited copy for a runner that does not load on a v0.2.16 Studio). It is preserved in git history and in the baseline tag.
- The earlier audit tests were replaced by regression tests; each of the 11 baseline defects that were asserted as `xfail` is now covered by a passing regression test.

## 5. Mapping of the baseline audit findings

| Baseline finding | Status after remediation |
|---|---|
| F-01 HIGH quadratic HTML regexes | Fixed (Finding A) |
| F-02 weak quotation guard | Fixed (B.2) |
| F-03 prompt interpolation | Fixed (B.1) |
| F-04 transient outage becomes terminal | Fixed (Finding C) |
| F-05 anyone can finalise immediately | Fixed (Finding C) |
| F-06 independence not deterministic | Substantially fixed, with the residual risks listed in B.3/B.4 |
| F-07 commitments incomplete | Fixed |
| F-08 LLM-claimed dates not verified | **Open (LOW)**: dates are still compared across nodes but not matched to page text |
| F-09 typecheck exit 1 | Fixed |
| F-10 dead code | Fixed |
| F-11 `run_nondet` vs official page | Changed to `run_nondet_unsafe` |
| F-12 liveness of exact comparison | **Open (informational)**: unmeasured on real validators |
| F-13 web-layer semantics, F-14 spam/identity, F-15 epistemic limits | **Open (informational)** |

## 6. Not verified (explicit)

1. **Studio / network deployment of this exact file and schema loading there: NOT RUN.** `tests/integration` collects 4 tests; none was executed.
2. **Real multi-validator consensus, leader rotation, appeals: NOT RUN.** Direct Mode runs one leader and one validator call against mocks.
3. **Real LLM behaviour** (prompt-injection resistance, agreement rate of independent models on classification and entailment, JSON compliance): NOT RUN. Exact-agreement liveness is unmeasured and can leave events `OPEN`.
4. **Execution on the GenVM WASM runner** (CPU/memory metering, timeouts, closure serialisation by the real runtime): not verified. Direct Mode runs on host CPython; `cloudpickle`-based pickling of the leader/validator closures passes.
5. **Documentation coverage:** see `TRUTHANCHOR_API_COMPATIBILITY.md` (section 8). Read in this remediation: *Error Handling*. *Web Access*, *Transaction Context* and *Storage* were read in earlier phases and were not re-fetched here; the *Testing Intelligent Contracts* and *GenLayer Test API* pages were **not read** at all. The installed SDK source and the installed `genlayer-test` source were used as the authority for the APIs, and `hasattr` probes executed in Direct Mode confirmed `gl.vm.UserError` and `gl.vm.run_nondet_unsafe` exist and `gl.UserError` does not.
6. `genlayer-test` 0.29.2 limitation: `warp()` updates `datetime.now()` but not `gl.message_raw["datetime"]` after deployment; the tests move the transaction clock through `set_time` in `tests/direct/helpers.py`.

## 7. Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Old quadratic/unbounded path no longer used | Met | Removed; `test_old_vulnerable_path_is_gone` |
| Hostile 300 KiB processed or rejected under an explicit bound without quadratic work | Met | S01/S02; work ratio constant at 75/150/300 KiB; 0.197 s worst case |
| Linear claim supported by implementation and tests, not only a benchmark | Met | Work counter + monotone-cursor argument |
| Callers cannot redefine prompt, task or evidence policy | Met (structurally) | S03; no public method takes policy text; real model behaviour NOT RUN |
| Prompt/delimiter injection cannot change control logic | Met within the contract | S03/S04; model-level resistance NOT RUN |
| Trivial/irrelevant excerpts cannot corroborate | Met | S05 |
| Exact quotation/source correspondence verified | Met | `test_B2_stored_excerpt...`; offsets not used (documented) |
| Identical content on different domains is not independent | Met | S06 |
| Hostnames alone are not proof of independent publishers | Met | S07 |
| Validators independently verify decision-bearing evidence | Met | A11/A13 (80 adversarial tests; mutations M11, M15 killed) |
| All-source 5xx / timeouts leave the event retryable and non-terminal | Met | S08/S09 |
| Third party cannot finalise before eligibility | Met | S10 |
| Missing evidence is never falsity | Met | S13 |
| State written only after accepted consensus | Met | `test_C23`; code structure |
| Repeated calls cannot overwrite a finalised event | Met | S15 |
| Source and deployment artifacts consistent | Met | `TRUTHANCHOR_DEPLOYMENT_VERIFICATION.md` (18 PASS; 14 tamper tests) |
| Every mandatory regression test has an actual result | Met | `TRUTHANCHOR_SECURITY_TEST_MATRIX.md` |
| All available required checks pass or blocked checks are identified | Met | section 6 lists every blocked/not-run check |

## 8. Submission status

In the verified environment the corrected source and the deployment package satisfy every acceptance criterion above, and every check that could be executed
was executed and passed. This is **not** a claim that the contract is secure: it has not been deployed, real consensus and real LLM behaviour have not been
exercised, and the residual risks in sections 1-3 and 6 stand. The first step on a real Studio should be loading `contracts/truth_anchor.py` and running the integration tests.
