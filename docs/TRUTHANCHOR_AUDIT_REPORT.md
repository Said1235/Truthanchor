# TruthAnchor - Independent Security, Logic and Implementation Audit

| | |
|---|---|
| **Audited file** | `contracts/truth_anchor.py` (827 lines) |
| **SHA-256** | `6fdf243441b1fe025fa04485cf122e0df67221f3c717531bf9f87e3126ae3095` (verified identical before and after the audit; the file was never modified) |
| **Target** | SDK generation A: header `# v0.2.16` + `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |
| **Audit date** | 2026-11-14 |
| **Phase** | Phase 1, read-only. No remediation has been applied. Remediation proposals (section 17) await explicit approval. |

## 1. Executive summary

**Overall assessment: NOT READY - HIGH-PRIORITY DEFECTS FOUND.**

TruthAnchor's consensus design is fundamentally sound. The validator does not trust the leader: it re-fetches every registered
URL, re-runs the LLM analysis with the same prompt, and compares every decision-bearing field exactly (retrieval status,
classification, source type, independence group, dates, derived outcome). It never reads `.calldata` before confirming
`gl.vm.Return`, it recomputes all commitments, and the contract re-validates the accepted result deterministically before it
writes anything. 15 explicit leader-versus-validator contradiction scenarios were executed and all were rejected, including
forgeries that are internally consistent (valid structure, valid commitments, outcome derived from their own findings).
Mutating the validator into a naive structure-only check makes 13 of 36 adversarial tests fail, so the tests do detect the
weakness the audit brief warns about.

One **HIGH** finding blocks readiness and six **MEDIUM** findings (F-02 to F-07) should be resolved or consciously accepted before a real
deployment. In total: 1 HIGH, 6 MEDIUM, 3 LOW and 5 INFORMATIONAL:

| ID | Severity | One-line summary |
|---|---|---|
| F-01 | **HIGH** | HTML stripping regexes are quadratic: a hostile 300 KB page costs about 40 s of CPU per node (extrapolated from measurements). |
| F-02 | MEDIUM | The quotation guard is vacuous: any substring (even `"the"`), or a real but irrelevant sentence, counts as supporting evidence. |
| F-03 | MEDIUM | User-controlled text (proposition, description, URLs) is interpolated into the LLM prompt without delimiting or escaping. |
| F-04 | MEDIUM | A transient outage of all sources is finalised as a **terminal** INCONCLUSIVE. |
| F-05 | MEDIUM | Anyone can finalise a freshly registered event as terminal INCONCLUSIVE before its sources are published. |
| F-06 | MEDIUM | Source independence is not established deterministically (identical pages on different hosts count as independent). |
| F-07 | MEDIUM | Commitments omit `title`, `source_type` and `independence_group`, which are stored and decision-bearing. |
| F-08 | LOW | LLM-claimed publication/update dates are stored without being found in the page. |
| F-09 | LOW | `genvm-lint typecheck` exits 1 because `_err` is not annotated `NoReturn`. |
| F-10 | LOW | Dead code in `_check_structure` and `leader_fn`. |
| F-11 to F-15 | INFORMATIONAL | Documentation discrepancy on `run_nondet`, liveness, unverified web semantics, spam and caller identity, epistemic limits. |

No CRITICAL finding was identified. Nothing in this audit proves that a deployment to a real Studio or network works:
**Studio deployment, integration tests and real multi-validator consensus were NOT EXECUTED** (section 15, section 18).

## 2. Exact SDK and runner versions

| Item | Value | Evidence |
|---|---|---|
| Contract header | `# v0.2.16` / `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` | `contracts/truth_anchor.py` lines 1-2 |
| GenVM bundle | `v0.2.16` (contains the runner above) | `genvm-lint` cache and `genlayer-test` cache; `GENVM_VERSION=v0.2.16` |
| SDK library actually loaded by the tests | `py-lib-genlayer-std/11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v` | `genlayer.__file__` printed from a test; module has `gl.vm.run_nondet`, has no `run_nondet_default`, has no `gl.contract` |
| Linter | `genvm-linter` 0.11.0 (PyPI) | `pip list` |
| Test framework | `genlayer-test` 0.29.2 | `pip list` |
| Other | Python 3.12.3, pytest 9.2.0, `cloudpickle` 3.1.2 | `pip list`, `python --version` |
| Official boilerplate | `genlayerlabs/genlayer-project-boilerplate` `main`; its 43 direct tests also pass in this environment | executed |

Four runner hashes were seen during the engagement; only `1jb45aa8...` is the audit target (see `TRUTHANCHOR_API_COMPATIBILITY.md`).
The earlier build for runner `kzybg95x...` is a separate, **unaudited** variant under `variants/`.

## 3. Files inspected

All inspected in full: `contracts/truth_anchor.py` (every line), `tests/direct/conftest.py`, `helpers.py`, `test_registration.py`,
`test_resolution.py`, `test_validator_adversarial.py`, `test_helpers.py`, `tests/integration/test_deploy_and_flow.py`, `abi.json`,
`requirements-dev.txt`, `pytest.ini`, the SDK source for runner `1jb45aa8...` (`gl/vm.py`, `gl/nondet/web.py`,
`gl/nondet/__init__.py`, `gl/__init__.py`, `py/keccak.py`, storage modules), the boilerplate (`CLAUDE.md`, `football_bets.py`,
`PatternTest.py`, `requirements.txt`) and the operator-supplied playbook and skills notes.

Imported modules in the contract: `html`, `json`, `re`, `dataclasses.dataclass`, `datetime`, and `from genlayer import *`.
No `hashlib`, `os`, `sys`, `random`, `float` or network library is imported.

## 4. Functional audit

| Requirement | Result | Evidence |
|---|---|---|
| Three outcomes CONFIRMED_TRUE / CONFIRMED_FALSE / INCONCLUSIVE; lifecycle OPEN / RESOLVED_TRUE / RESOLVED_FALSE / INCONCLUSIVE | Implemented (`_derive_outcome` L234-261; `LIFECYCLE_NAMES`, `OUTCOME_NAMES` L28-29) | `test_resolution.py`, `test_helpers.py` truth table |
| CONFIRMED_TRUE needs sufficient admissible supporting evidence | Needs at least 2 independent groups with SUPPORTS and none CONTRADICTS (R1) | tests |
| CONFIRMED_FALSE needs sufficient admissible contradicting evidence | Needs at least 2 independent groups with CONTRADICTS and no SUPPORTS (R2) | tests |
| Absence of evidence never yields FALSE | Verified exhaustively over all combinations of classes {CONTEXT_ONLY, INSUFFICIENT, UNAVAILABLE} | `test_absence_of_evidence_never_yields_false`, D06 |
| Failed HTTP is not FALSE | Verified (404/503/empty/exception all become UNAVAILABLE) | D06, G03, `test_unavailable_sources_never_mean_false` |
| Failed LLM call is not a factual outcome | Verified: `[LLM_ERROR]`, event stays OPEN | G01, 9 malformed-output tests |
| Consensus failure is not a successful resolution | Verified by construction and by test G04 (no state written before `run_nondet` returns) | G04 |
| Cannot resolve before registration | `event not found` | `test_resolution_errors` |
| Cannot be resolved twice | `event is not open` (checked before and after the non-deterministic block, L688 and L717) | B03, `test_resolution_errors` |
| Proposition, sources and interval immutable | No public method mutates them; `resolve_event` reads only stored copies (L690-697) | code inspection; C07, C08 |
| Evidence cannot cross events | Closures capture only the copied values of one event; all storage access is keyed by `event_id` | B03, B04, interleaving test |
| Failed resolution leaves no partial state | All writes occur after consensus and after deterministic re-validation (L713-742) | G01, G02, G04 |
| New investigation keeps the old record | `parent_event_id`; parent must exist, be non-OPEN and share the proposition (L650-657) | B06, re-verification test |
| History retrievable | `get_event(id)`; `list_event_ids` | B01, B06 |

**Contradictions between intent and implementation:** none on the core semantics. Design-level tensions (terminal INCONCLUSIVE
versus transient failures, permissionless timing) are recorded as F-04 and F-05.

## 5. Architecture audit

- Single contract, two writes (`register_event`, `resolve_event`), five views. No owner, no admin, no payable method.
- Pure helper functions at module level; the contract class contains only storage, the constructor and public methods. All
  non-deterministic logic is isolated in `_fetch_source`, `_analyze` and the two closures inside `resolve_event`.
- Storage: `next_event_id: u256`, `events: TreeMap[u256, EventRecord]`; both dataclasses use `@allow_storage` at module level.
- Registration is fully deterministic (no LLM call); resolution is the only non-deterministic path.
- Risk: the leader/validator closures call module-level helpers. Direct Mode's pickling check passes (with the real
  `cloudpickle`), but the real GenVM serialisation of closures is not verified (section 18).

## 6. Equivalence Principle audit (highest priority)

Official reference: *The Equivalence Principle*, https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle
(read in full). Key requirements from that page, and the contract's conformance:

| Official requirement | Contract behaviour | Verdict |
|---|---|---|
| "Never treat the leader's result as trusted input"; validators must verify substance using evidence other than the leader's answer | `validator_fn` re-fetches all registered URLs and re-runs the same LLM task (L708) | Conforms |
| A validator that only checks JSON shape, enum, non-empty summary or confidence in range "is not performing consensus" | `_validator_agrees` (L550-566) compares all decision fields; `_check_structure` is only the first gate | Conforms |
| Compare decision fields, not free text | Free-text LLM explanation was deliberately removed from the consensus result (design D3) | Conforms |
| Check `gl.vm.Return` before `.calldata` | L704 `isinstance(leader_res, gl.vm.Return)` precedes `.calldata` (L709) | Conforms |
| Handle `UserError` / `VMError` leader results | Non-`Return` leader results are re-derived and compared by `compare_user_errors` (L569-572); `[LLM_ERROR]` always disagrees (forces rotation) | Conforms; VMError path not executable in Direct Mode (G06) |
| Do not use numeric tolerances that cross decision boundaries | No scores, confidences or tolerances exist; all comparisons are exact | Conforms (audit section 12 N/A) |
| "Reject when in doubt" | Any mismatch returns False | Conforms |
| "The accepted leader result is the value your contract receives"; validator intermediate answers are not persisted | The contract stores only the leader result after it passes `_check_structure` (L713-742) | Conforms |
| Docs recommend `run_nondet_unsafe` for custom leader/validator logic | The contract uses `run_nondet` (sandboxed) | Discrepancy, see F-11 |

### 6.1 Weak-consensus patterns (audit section 11)

| Pattern | Present in TruthAnchor? |
|---|---|
| Validator checks only status / outcome / JSON validity / enum / confidence / summary / category / score bucket | **No** |
| Accepts arbitrary differences in actionable findings | **No** (exact equality of classification, type, group, dates, retrieval status) |
| Ignores source evidence | **No** (re-fetch; excerpt/title presence check) |
| Ignores missing or contradictory fields | **No** (exact key sets; contradictions change classification) |
| Accepts empty evidence | **No**: finding count must equal the registered source count; an empty excerpt is only allowed for non-conclusive classifications |
| Accepts a malformed source commitment | **No** (regex plus full recomputation) |
| Compares only a subset of decision-bearing fields | **No**, with two nuances: excerpt and title are checked for *presence* only (F-02), and commitments exclude three stored fields (F-07) |

### 6.2 Verification of the leader result field by field

| Field | How it is bound to the consensus decision |
|---|---|
| `event_id`, `proposition`, `schema_version`, `criteria_version` | Equality with the values read from storage (L485-488) |
| `registered_url`, `publisher_host` | Equality with the registered URL and the host recomputed from it (L502) |
| `retrieval_status` | Exact equality with the validator's own fetch (L557) |
| `classification` | Exact equality with the validator's own LLM-derived value (L557) |
| `source_type` | Exact equality (L557) |
| `independence_group` | Exact equality; groups are host-based plus LLM merge links (L557, L279-305) |
| `publication_timestamp`, `update_timestamp` | Exact equality (L558); see F-08 and the liveness note F-12 |
| `excerpt`, `title` | Normalised substring present in the validator's own page text (L561-564); see F-02 |
| `source_commitment`, `evidence_commitment` | Recomputed from the fields (L521, L528); see F-07 |
| `independent_source_assessment` | Recomputed (L526, L540) |
| `proposed_outcome`, `outcome_reason` | Equal to the outcome derived by the validator from its own findings (L565-566) |
| Event interval | Not a leader field; used only in the prompt; the stored values feed `result_commitment` computed by the contract after consensus |

## 7. Leader to validator to storage data flow

```
resolve_event(event_id)                          [deterministic, runs on every node]
  |- reject if event missing or lifecycle != OPEN                       (L685-689)
  |- copy storage -> memory: urls, proposition, description, start, end (L691-696)
  |- now_ts = tx datetime (gl.message_raw["datetime"])                  (L697)
  |
  |- gl.vm.run_nondet(leader_fn, validator_fn, compare_user_errors)     (L711)
  |     LEADER                                   VALIDATOR (each, sandboxed)
  |     _analyze():                              if leader result is not gl.vm.Return:
  |       web.get(url) x N (<=5)                     re-run _analyze(); raise same UserError or return False
  |       -> RS_* + normalised text              else:
  |       exec_prompt(json) -> _parse_llm            mine = _analyze()          (independent fetch + LLM)
  |       -> classification, type, groups            _check_structure(leader)   (exact keys, types, hashes, outcome)
  |       -> excerpt guard, dates                    compare 6 decision fields per source
  |       -> source_commitment                       excerpt/title present in MY page text
  |     _build_result() -> dict (calldata)           outcome == derive(MY findings)
  |                                                  -> True / False
  |   majority True  -> result = leader dict
  |   majority False -> leader rotation -> still no agreement: transaction undetermined, NO state change
  |
  |- _check_structure(result, ...)  again, deterministically            (L714)
  |- re-check lifecycle == OPEN                                         (L716-718)
  |- write evidence[], commitments, lifecycle, reason, timestamp        (L723-742)
  `- return outcome name
```

No storage is written before `run_nondet` returns. No lookup of "latest" record occurs anywhere.

## 8. Source integrity audit

| Check | Result |
|---|---|
| URLs immutable | Yes: no mutator; `resolve_event` reads the stored list; caller supplies only `event_id` |
| Duplicates rejected | Yes, after normalisation (lower-case scheme/host, strip `www.`, default port, fragment, trailing slash) (L150-162) |
| Scheme / emptiness / length / count | `https` only; 12..500 chars; 2..5 sources; total string at most 2504 chars checked before splitting |
| Internal / IP / credential hosts | Rejected (L127-141) |
| Caller cannot substitute URLs at resolution | Yes (C06, C07 and URL-substitution tampering tests) |
| Independence | Host-exact grouping plus LLM merge-only links. Not deterministic for identical content: **F-06** |
| Primary vs secondary vs syndicated | `source_type` vocabulary is recorded; syndication relies on the LLM flag `same_origin_as` (D02 passes; D04 shows the gap) |
| Quotations bound to a source | Excerpt must be a normalised substring of *that* source's text (C06 passes), but a trivial or irrelevant substring suffices: **F-02** |
| Offsets | Not used; presence is checked on normalised text (casefold, whitespace collapse, typographic quotes mapped) |
| Commitments | Keccak256 over canonical JSON (sorted keys, compact separators, ASCII-escaped). Incomplete coverage: **F-07**. They prove integrity of the stored record, not publisher authenticity or truth |
| Hash API | `Keccak256` from `genlayer` (verified in SDK source; `hashlib` is not used) |

## 9. Event identity and concurrency audit

- `event_id` comes from the stored counter `next_event_id` (`u256`, starts at 1), guarded by `_check_id_space` and a membership check before insertion (L658-662). It is never derived from collection size, wallet lists, last element or transaction order.
- Every read and write is keyed `events[event_id]`. There is no global "latest result".
- Failed registrations do not consume ids (B05). Two callers, overlapping events and interleaved resolutions keep results bound to their ids (B02, B03, B04, interleaving test).
- Double resolution is rejected before and after the non-deterministic block.
- Re-verification creates a new linked record; the parent is unchanged (B06).
- Caveat: Direct Mode is single-threaded; true concurrent transaction ordering on a network was not exercised.

## 10. Storage and type audit

Reference: *Storage Quick Reference* https://docs.genlayer.com/developers/intelligent-contracts/features/storage (read in full): storage fields declared
with annotations; `DynArray[T]` / `TreeMap[K, V]` instead of `list` / `dict`; sized integers instead of `int`; all generics fully
specified; storage is zero-initialised; copy storage to memory before non-deterministic blocks.

| Check | Result |
|---|---|
| Fields declared in the class body with annotations | Yes (`next_event_id`, `events`) |
| No dynamically created persistent fields | Yes |
| No `dict`/`list`/`int`/`float` in storage | Yes |
| Generics fully specified | Yes (`TreeMap[u256, EventRecord]`, `DynArray[str]`, `DynArray[SourceEvidence]`) |
| Dataclasses use `@allow_storage` | Yes; the linter's `E014` does not fire on this generation |
| TreeMap key type | `u256`; the linter (rule `E018`) accepts only `str, Address, u32, u256, i32, i256, bytes` |
| Address | One field, `submitter`, assigned from `gl.message.sender_address`; no `Address` parameters; no integer or string conversions exist |
| Numeric types | ids `u256`, timestamps `u64`, versions `u32`, enums `u8`; each assignment uses an explicit constructor; every integer parameter is range-checked (L639-643) |
| Overflow | Counter guard `_check_id_space` (unit-tested at the boundary) |
| Copy storage to memory before non-determinism | Done manually for scalars and a list comprehension for `source_urls` (L690-697), as the doc recommends |

## 11. Constructor and deployment audit

- `def __init__(self):` with one statement, `self.next_event_id = u256(1)` (L618-619). Zero parameters.
- `genvm-lint schema` output was inspected, not only its exit code: `"ctor": {"params": [], "kwparams": {}}` and exactly 7 public methods. It is byte-identical to the shipped `abi.json`.
- Direct deployment with no arguments, initial state and post-deployment registration: A01, A02 (PASS).
- **Studio deployment: NOT EXECUTED.** No Studio was available. A previous build targeting a different runner failed to load in the operator's Studio ("schema not loaded"); that failure is explained by a runner-generation mismatch and does not apply to this file, but loading of *this* file in the operator's Studio is unverified.

## 12. Input validation audit

Every public input is validated inside the contract. All of the following were executed:

empty / whitespace-only / short / long proposition; long description; invalid or `bool` timestamps; start after end; end in the future; end at `2**64-1`
and `2**64`; missing, single, duplicate-after-normalisation, six, `http`, credential, IP, `localhost`, `.internal`, IPv6, bad-port,
over-long and non-ASCII URLs; oversized `source_urls`; unknown, open and mismatched parents; parent id `2**256-1` and `2**256`;
nonexistent, huge and zero event ids; resolving an already resolved event; `list_event_ids` with out-of-range arguments.

Not accepted as proof: redirects, DNS rebinding and server-side request restrictions of the GenLayer web layer, which are
unverified (F-13).

## 13. Prompt-injection audit

Official reference: *Prompt Injection* https://docs.genlayer.com/developers/intelligent-contracts/security-and-best-practices/prompt-injection (read in full):
restrict inputs, construct prompts inside the contract rather than from free-form user input, restrict outputs, keep logic simple,
consider human-in-the-loop.

| Control | Status |
|---|---|
| Source text is delimited and labelled untrusted data | Yes (L331-334) |
| Page text cannot reproduce the real delimiter | **Incidentally yes**: `_norm` lower-cases page text, so an injected `<<<END SOURCE 0>>>` becomes lower-case and never equals the real one (E01 PASS). This is a side-effect of normalisation, not a designed control; it would silently disappear if `_norm` stopped using `casefold` |
| Output is constrained | Yes: closed vocabularies; `_parse_llm` rejects anything else (`[LLM_ERROR]`) |
| A model that obeys an injection still cannot force a conclusive outcome without a real quotation | Yes (E02, E03 PASS) |
| Fabricated quotations are rejected | Yes (C05, C06, E03) |
| Validator independently assesses the result | Yes, but with the same prompt and likely the same model family, so manipulation that fools both models identically is not detectable by consensus |
| User-controlled text is kept out of the prompt structure | **No**: proposition, description and URLs are concatenated verbatim (L331, L336, L337): **F-03** |
| Human-in-the-loop | Not present |

The behaviour of a real LLM facing an injected page cannot be tested with mocks: **NOT EXECUTED**.

## 14. Error-handling audit

| Failure | Behaviour | Test |
|---|---|---|
| Leader LLM failure / malformed JSON / wrong types / missing fields / bad enum | `[LLM_ERROR]`, revert, event OPEN | G01 and 9 parametrised cases |
| Validator LLM failure | Sandbox error compared via `compare_user_errors`; `[LLM_ERROR]` never agrees | `test_compare_user_errors_policy` |
| Web exception | RS_FETCH_ERROR / UNAVAILABLE, never FALSE | G03 |
| HTTP 4xx / 5xx / 3xx / empty body | RS_HTTP_ERROR / RS_EMPTY / UNAVAILABLE | D06, D07 |
| Consensus not reached | Transaction undetermined by the protocol; contract state untouched | G04 (simulated by raising from `run_nondet`) |
| VM error from leader | Same path as other non-`Return` results | **NOT EXECUTED** (G06) |
| Retry after failure | Resolves the same id with no duplicate evidence | G02 |
| All sources down | Finalised as terminal INCONCLUSIVE | **F-04** |

## 15. Test execution results

All commands were run from the repository root with `GENVM_VERSION=v0.2.16`. Raw logs were kept during the audit.

| Command | Exit | Result |
|---|---|---|
| `genvm-lint check contracts/truth_anchor.py --json` | 0 | `ok: true`; lint passed 3; validate: contract `TruthAnchor`, 7 methods (5 view, 2 write), `ctor_params: 0` |
| `genvm-lint lint contracts/truth_anchor.py --json` | 0 | `ok: true`, `passed: 3`, no warnings |
| `genvm-lint validate contracts/truth_anchor.py --json` | 0 | `ok: true`, 7 methods, `ctor_params: 0` |
| `genvm-lint typecheck contracts/truth_anchor.py` | **1** | reports `truth_anchor.py:368: Object of type "None" cannot be used as iterable value [reportOptionalIterable]` then "0 error(s), 0 warning(s)" (**F-09**) |
| `genvm-lint schema contracts/truth_anchor.py --output abi.json` | 0 | constructor `params: []`; 7 methods; identical to shipped `abi.json` |
| `pytest tests/direct/` (pre-existing) | 0 | 128 passed |
| `pytest tests/direct/` (full, with audit tests) | 0 | **175 passed, 2 skipped, 11 xfailed**, 0 failed |
| `pytest tests/direct/test_audit_adversarial.py` | 0 | 47 passed, 2 skipped, 11 xfailed |
| Mutation: replace validator with structure-only check | - | 13 of 36 `test_validator_adversarial.py` tests fail; genuine validator passes 36 |
| Boilerplate `pytest tests/direct` | 0 | 43 passed |
| `gltest tests/integration -v -s` | - | **NOT EXECUTED** (no Studio). `pytest --collect-only` collects 3 tests |
| Studio deployment | - | **NOT EXECUTED** |

Skipped: G06 (VMError leader result cannot be synthesised in Direct Mode) and G07 (real multi-validator consensus). The 11
xfailed tests each assert the safe behaviour and fail today; each is mapped to a finding. Full detail:
`TRUTHANCHOR_AUDIT_TEST_MATRIX.md`. Direct Mode runs on the host CPython, not on the GenVM WASM runner.

## 16. Findings

Line numbers refer to the audited file (SHA-256 above).

### F-01 [HIGH] HTML stripping regexes have quadratic complexity

- **Where:** `_SCRIPT_RE` L80, `_TAG_RE` L81, `_html_to_text` L179-185, called from `_fetch_source` L320 on up to `MAX_BODY_BYTES = 300000` bytes.
- **Behaviour:** `<(script|style)\b.*?</\1\s*>` rescans to the end of the input for every unterminated `<script`; `<[^>]*>` rescans to the end for every `<` without a closing `>`. Cost grows with the square of the page size.
- **Measured** (CPython 3.12 in the audit sandbox, same patterns and flags as the contract): `<script ` repeated: 16 KB 0.11 s, 32 KB 0.49 s, 64 KB 1.90 s (doubling the input multiplies the time by about 4). `<` repeated: 8 KB 0.04 s, 16 KB 0.12 s, 32 KB 0.41 s. Extrapolated to the 300 KB cap: roughly **40 s** (script) and **36 s** (`<`) per fetch, on the leader and on every validator.
- **Scenario:** an attacker registers an event whose source is a page they control (or a user-generated page they can influence) containing a repeated `<script ` or `<`, then calls `resolve_event`. Every node burns CPU; the transaction either times out or is rejected, the event cannot be resolved, and the attacker can repeat the attempt. The amplification (cheap static page to large validator work) is the aggravating factor.
- **Expected:** processing time linear in page size.
- **Official basis:** audit brief section 26 (bounded resource usage). The GenLayer documentation read for this audit does not document the runner's metering or timeouts: **how GenVM limits such work is unverified**, and the WASM runner is likely slower than the CPython used for the measurement.
- **Proof:** `test_FND01_html_stripping_is_linear_time` (xfail strict; ratio about 4 versus the safe bound of 3).
- **Remediation (prototyped, see section 17).**

### F-02 [MEDIUM] The quotation guard does not bind the excerpt to the claim

- **Where:** L435-437 (degrade rule), L440-441 (storage), L561-564 (validator presence check).
- **Behaviour:** an excerpt is accepted if its normalised form is a substring of the page text. There is no minimum length and no check that it supports the classification. `"the"` passes; a real but irrelevant sentence passes.
- **Scenario:** a model that hallucinates SUPPORTS can satisfy the only deterministic anti-hallucination guard with a trivial or unrelated string. Outcome acceptance still requires the validator's own LLM to classify SUPPORTS, so a malicious *leader* cannot force an outcome by this route; the damage is to the **auditability** of stored evidence and to the strength of the hallucination guard.
- **Expected:** audit brief section 16: "the excerpt supports the associated classification."
- **Proof:** `test_FND02_trivial_excerpt...`, `test_FND02b_irrelevant_excerpt...` (xfail strict).

### F-03 [MEDIUM] User-controlled text is concatenated into the prompt unescaped

- **Where:** `_build_prompt` L331 (URL), L336 (`PROPOSITION:`), L337 (`CONTEXT:`).
- **Behaviour:** newlines and delimiter look-alikes in the proposition, description or URL reach the prompt unchanged, so a submitter can add instruction lines or spoof `<<<END SOURCE n>>>`.
- **Official basis:** *Prompt Injection* page: restrict inputs and construct prompts inside the contract rather than from free-form user input.
- **Scenario:** a submitter who already chooses the sources can steer both the leader's and the validators' model (the same prompt reaches all of them), which consensus cannot detect.
- **Proof:** E04, E05, E06 (xfail strict). E01, E02 and E03 pass, showing which parts are safe.

### F-04 [MEDIUM] A transient outage becomes a terminal factual state

- **Where:** `_fetch_source` L311-323 (every exception and every non-2xx status is mapped to UNAVAILABLE), `_derive_outcome` L259-260 (reason 2), `resolve_event` L737-743.
- **Behaviour:** if all sources are unreachable when the leader and the validators happen to fetch, validators agree on UNAVAILABLE and the event becomes a **terminal** INCONCLUSIVE with reason 2.
- **Scenario:** a CDN or network outage during resolution permanently closes the record; a new linked event is required.
- **Official basis:** the Equivalence Principle page defines a `[TRANSIENT]` error class ("temporary failures (timeouts, 5xx)"), for which agreeing validators leave state unchanged.
- **Note:** the specification says an accepted INCONCLUSIVE is terminal; this finding concerns whether *infrastructure* failures should count as a factual INCONCLUSIVE. Changing it needs a specification decision.
- **Proof:** `test_FND04_...` (xfail strict).

### F-05 [MEDIUM] Any caller can finalise an event immediately

- **Where:** `resolve_event` L683-743 has no caller or time restriction.
- **Scenario:** right after registration, before the submitter's pages are published, a third party calls `resolve_event`; the result is a terminal INCONCLUSIVE (combined with F-04).
- **Proof:** `test_FND05_...` (passes: it documents the behaviour). The specification mandates permissionless resolution, so this is a design risk, not a deviation.

### F-06 [MEDIUM] Independence is not established deterministically

- **Where:** `_groups` L279-305, used at L412; L557 compares only the LLM-derived group.
- **Behaviour:** grouping is exact-host equality plus LLM merge links. Byte-identical pages on different hosts, mirrors, and same-organisation subdomains count as independent unless the model flags them.
- **Scenario:** two sites controlled by the submitter, or two mirrors of one press release, produce CONFIRMED_TRUE.
- **Official/brief basis:** audit brief section 15: if independence cannot be established the contract should return INCONCLUSIVE rather than claim independent corroboration.
- **Proof:** D04 (xfail strict). D02 passes (a model-flagged syndicated copy is merged).

### F-07 [MEDIUM] Commitments do not cover all decision-bearing stored fields

- **Where:** `_source_commitment` L196-210 and `_result_commitment` L217-231 omit `title`, `source_type` and `independence_group`.
- **Behaviour:** `independence_group` decides the outcome and is stored but is not committed.
- **Proof:** `test_FND07_...` (xfail strict).
- **Note:** a commitment proves integrity of bytes, not publisher authenticity or truth; this is unchanged by the fix.

### F-08 [LOW] LLM-claimed dates are not checked against the page

- **Where:** `_parse_date` L264-276, L444-445, compared exactly at L557-558.
- **Behaviour:** a plausible `YYYY-MM-DD` that does not occur in the page is stored; a future date is zeroed. Exact comparison across two LLMs also adds a liveness risk (F-12).
- **Proof:** D10 (xfail strict). D09 passes (absent dates are 0).

### F-09 [LOW] `genvm-lint typecheck` exits 1

- **Where:** `_err` L85 has no `NoReturn` annotation, so pyright treats code after `_err(...)` as reachable and flags L368 (`reportOptionalIterable`).
- **Verified fix (on a copy):** `import typing` and `def _err(kind: str, msg: str) -> typing.NoReturn:` gives "No type errors found" and `genvm-lint check` still reports `ok: true`, `ctor_params: 0`.
- **Proof:** `test_FND09_typecheck_is_clean` (xfail strict).

### F-10 [LOW] Dead code

- L536 assigns `s2, c2 = s, c` and never uses them; `leader_fn` binds an unused `_texts` (L700). No behavioural impact.

### F-11 [INFORMATIONAL] `run_nondet` versus `run_nondet_unsafe`

The official Equivalence Principle page recommends `run_nondet_unsafe` with explicit error handling for custom leader/validator
patterns and lists `run_nondet` for "convenience functions and simple validators". The SDK docstring for the installed runner
describes `run_nondet` as the recommended API. The contract uses `run_nondet` with a custom `compare_user_errors`. No defect was demonstrated
(validators that raise are compared with the leader error, never silently accepted), but the choice differs from the page's
advice and its behaviour on real validator errors was not exercised.

### F-12 [INFORMATIONAL] Liveness is bounded by exact comparison

Exact agreement on classification, type, group and dates between independent LLMs can fail often enough to exhaust leader rotations;
the transaction then becomes undetermined and the event stays OPEN. This is safe (no wrong result is accepted) but unmeasured.

### F-13 [INFORMATIONAL] Unverified web-layer semantics

Redirect following, timeouts, maximum response size, TLS handling and SSRF restrictions of `gl.nondet.web.get` are not documented
in the pages read. The contract treats 3xx as UNAVAILABLE (D07). Behaviour on a real network is unverified.

### F-14 [INFORMATIONAL] Spam, growth and caller identity

Registration is unlimited and unpriced at the contract level; identical registrations are allowed; storage growth and fees were not
analysed. `submitter` is the immediate caller (`gl.message.sender_address`), which for contract-to-contract calls is the calling contract,
not the originating wallet.

### F-15 [INFORMATIONAL] Epistemic limits

The submitter chooses the sources, so an oracle result is only as trustworthy as those pages. A successful audit does not
prove that the oracle returns the truth; CONFIRMED_* means "supported/contradicted by the registered evidence under criteria v1".

## 17. Remediation recommendations (none applied; awaiting approval)

| Finding | Smallest safe change | Needs a spec decision? |
|---|---|---|
| F-01 | Replace the two regexes with a single-pass linear scanner (find `<`; find `>` once; if no further `>` exists treat the remainder as text; on an unterminated `script`/`style` stop). **Prototype verified on a copy:** same text as the regexes on normal HTML; 300 KB hostile inputs (`<script ` x37500, `<` x300000, `<a ` x100000) process in 0.3-0.5 ms versus 1.9 s for the original on only 64 KB. Optionally lower `MAX_BODY_BYTES`. | No |
| F-02 | Minimum excerpt length (for example 40 normalised characters) plus a validator-side check that the excerpt alone supports the classification (rubric-style LLM judgement, exact boolean compared), or require lexical overlap with proposition keywords. | No (tightens existing behaviour) |
| F-03 | Wrap proposition and description in explicit delimiters, collapse newlines, strip or replace `<<<`, `>>>` and control characters, and place URLs only as `id` references; consider dropping `description` from the prompt. | No |
| F-04 | If every readable-source attempt failed with fetch errors, 5xx or timeouts, raise `[TRANSIENT]` (validators agree on transient errors per the official pattern) and leave the event OPEN; keep 404/410 as UNAVAILABLE content. | **Yes** |
| F-05 | Add a minimum delay between registration and the first allowed resolution, or reserve the first window for the submitter. | **Yes** (spec says permissionless) |
| F-06 | Merge sources whose normalised page text hashes are identical (deterministic); document the remaining limitation for mirrors and subdomains; optionally add a versioned public-suffix list. | No (for the hash merge) |
| F-07 | Include `title`, `source_type` and `independence_group` in `_source_commitment`, and the groups in `_result_commitment`; bump `SCHEMA_VERSION`. | No (no deployed data yet) |
| F-08 | Require the date components to appear in the page text, or remove the dates from the consensus-compared set (store 0). | Minor |
| F-09 | `import typing` and annotate `_err` with `-> typing.NoReturn`. **Verified on a copy.** | No |
| F-10 | Remove the unused variables. | No |
| F-11 | Decide between keeping `run_nondet` (document why) or moving to `run_nondet_unsafe` with the official `_handle_leader_error` pattern; verify in Studio. | Decision |
| F-12 to F-15 | Measure agreement rate on real validators; document unverified web semantics; document spam and caller-identity limits. | No |

Suggested order: F-01, F-09, F-07, F-03, F-02, F-06, then the specification decisions F-04 and F-05. After the fixes, rerun the
full suite; the corresponding `xfail` markers will flip to XPASS and must be removed, and the three xfail-asserted behaviours become regression tests.

## 18. Remaining risks (not resolved by this audit)

1. **Studio / network deployment of this exact file is unverified.**
2. **Real multi-validator consensus, leader rotation and appeals were not exercised**; Direct Mode simulates only the leader and a single validator call.
3. **Direct Mode runs on host CPython**, not on the GenVM WASM runner: imports (`html`, `re`, `json`, `datetime`), closure serialisation and CPU/memory metering are verified only by the linter and the pickling check.
4. **Real LLM behaviour** (prompt injection, agreement rate, JSON compliance) is untested.
5. **Documentation not read** (listed in `TRUTHANCHOR_API_COMPATIBILITY.md`): any claim about those pages is unverified.
6. Runner-level limits (gas, time, memory, calldata, storage size) are not documented in the pages read; project limits in the contract are project-defined, not protocol limits.
7. Source authenticity: a registered page can state falsehoods convincingly (F-15).

## 19. Final readiness assessment

**NOT READY - HIGH-PRIORITY DEFECTS FOUND.**

Basis: one unresolved HIGH finding (F-01, resource-exhaustion amplification measured as quadratic). The consensus core meets the
audit's bar: all material leader-result fields are independently verified, contradictory evidence cannot be silently accepted
(15 of 15 scenarios rejected), exact event identity and history are maintained, storage types are valid, the constructor schema
is correct and all available direct tests pass.

Path to CONDITIONALLY READY: fix F-01 (small, prototyped), then resolve or explicitly accept the MEDIUM findings and rerun the suite.
Path to AUDIT PASSED additionally requires: execution of the integration tests and a Studio deployment of this exact file,
and a measurement of validator agreement with real LLMs. The absence of those executions is a standing limitation of this report.
