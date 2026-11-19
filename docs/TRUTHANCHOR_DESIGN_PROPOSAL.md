# TruthAnchor - Design Specification (criteria v2)

This document describes the design **as implemented** in `contracts/truth_anchor.py` (SDK generation A, runner `py-genlayer:1jb45aa8...`, GenVM v0.2.16).
It supersedes the criteria-v1 specification of the baseline `v0.1.0`; the differences and their reasons are in `TRUTHANCHOR_REMEDIATION_REPORT.md`.
Known limitations are listed there and in section 12.

## 1. Purpose and scope

TruthAnchor is a permissionless, evidence-based oracle for factual claims about **completed** public events. A user registers a precise proposition, a context
description, the UTC interval in which the event occurred and 2 to 5 public `https` URLs. After the eligibility time anyone may request resolution: the contract
retrieves the registered URLs, has an LLM classify the evidence under a fixed policy, has validators re-derive and verify that classification independently, applies
deterministic rules and stores a permanent result under the event's exact id.

It does **not**: predict the future, judge opinions, guarantee absolute truth, discover sources, or accept pasted text as evidence. The user's text defines *what*
is evaluated and is never evidence. There is no owner, administrator or role. The constructor takes **no arguments**.

## 2. Outcomes and lifecycle

| `lifecycle_status` | Name | Terminal |
|---|---|---|
| 0 | `OPEN` | no |
| 1 | `RESOLVED_TRUE` (`CONFIRMED_TRUE`) | yes |
| 2 | `RESOLVED_FALSE` (`CONFIRMED_FALSE`) | yes |
| 3 | `INCONCLUSIVE` | yes |

A resolution attempt returns one of `CONFIRMED_TRUE`, `CONFIRMED_FALSE`, `INCONCLUSIVE` or **`RETRYABLE`**. `RETRYABLE` is not a state: the event stays `OPEN` and only
`attempt_count`, `last_attempt_timestamp` and `last_attempt_reason` (5 = temporary source failure) are recorded.

`outcome_reason`: `0 NONE`, `1 INSUFFICIENT_INDEPENDENT_SOURCES`, `2 SOURCES_UNAVAILABLE`, `3 CONTRADICTORY_EVIDENCE`, `4 AMBIGUOUS_OR_NOT_ASSESSABLE`, `5 TEMPORARY_SOURCE_FAILURE` (attempt only).

`INCONCLUSIVE` is terminal only in these cases: proposition not assessable (4); contradictory independent evidence (3); insufficient independent evidence with every source
definitively processed (1); only permanently unavailable sources (2); or the closure condition (section 8). Results are never overwritten; a new investigation is a new
event linked by `parent_event_id` (same proposition, parent not `OPEN`). `final_outcome` is derived from `lifecycle_status`, not stored.

## 3. Eligibility and retry policy

- `earliest_resolution_timestamp = max(event_end + SETTLEMENT_DELAY (3600 s), registration + MIN_RESOLUTION_DELAY (600 s))`, stored at registration. The deterministic transaction time
  (`gl.message_raw["datetime"]`) must reach it, for every caller; otherwise `[EXPECTED] event is not yet eligible for resolution` and no state changes. The host clock, the LLM, source publication
  times and caller-provided times are never used.
- Retrieval statuses: `0 OK`; **temporary** (retryable): `4 HTTP_TEMPORARY` (5xx, 408, 425, 429), `6 NOT_FOUND` (404), `2 EMPTY` (2xx with an empty/unreadable body), `3 FETCH_ERROR` (any web-layer exception);
  **permanent**: `1 HTTP_PERMANENT` (3xx, 401, 403, 410, 451, other 4xx), `5 OVERSIZED`.
- While any source is temporary and the attempt is not final, the outcome is `RETRYABLE` (the LLM is not even called). Closure: after `RETRY_CLOSURE_ATTEMPTS = 3` recorded attempts **and**
  `RETRY_CLOSURE_WINDOW = 24 h` past the eligibility time, temporary states count as unavailable and the event may close (`INCONCLUSIVE` reason 2, or conclusively from the remaining evidence).

## 4. Source registration policy

`source_urls` is one `str`, 2 to 5 URLs separated by whitespace (whole string at most 2504 characters, checked before splitting). Each URL: 12-500 characters, printable ASCII, `https://` only,
no credentials, IP literals, `localhost`, `.local`/`.internal` hosts or IPv6 literals; valid port; duplicates detected on a normalised key (lower-case scheme/host, `www.`, default port, fragment and trailing `/` removed).
URLs are immutable; `resolve_event` takes only the event id.

## 5. Page retrieval and text extraction (bounded, linear)

`gl.nondet.web.get(url)`; the response is classified as in section 3. A readable body is processed by `_page_text_with_work`:

1. Raw body above `MAX_RAW_BYTES = 512 KiB` -> `OVERSIZED` without parsing.
2. `_strip_markup`: single pass, monotone cursor, no regular expressions: removes tags, comments, `script` and `style`; an unterminated construct drops only the tail; a lone `<` is text.
3. `_decode_entities`: single pass, named (`amp lt gt quot apos nbsp`) and numeric entities only, range-checked, output never rescanned (no recursion or expansion).
4. `_norm`: removes bidi/zero-width/control characters, maps typographic quotes and dashes, casefolds and collapses whitespace.
5. Extracted text above `MAX_TEXT_CHARS = 20 000` -> `OVERSIZED`; below 20 characters -> `EMPTY`.

The function returns a work counter bounded by `HTML_WORK_FACTOR = 5` times the input length; tests assert it for 19 hostile shapes at 75, 150 and 300 KiB.

## 6. Prompt construction and model output

The task and policy are fixed constants (`_POLICY`, `_ANALYSIS_SPEC`, `_ENTAIL_SPEC`). Everything untrusted (the proposition, page texts, excerpts and contexts) is carried in **one JSON line** (`DATA: ...`, ASCII-escaped).
The description and the URLs are not part of any prompt. Two model calls: **source analysis** (per source: `SUPPORTS`, `CONTRADICTS`, `AMBIGUOUS` or `IRRELEVANT`, a verbatim excerpt, source type, title, dates and
`same_origin_as` links; plus `proposition_assessable`) and **excerpt entailment** (each decision-bearing excerpt with up to 400 characters of context on each side). Output is validated strictly and never executed.

## 7. Evidence and independence

- **Excerpt policy** (necessary conditions): 40-300 characters, at least 6 words, at least 2 salient proposition tokens, present in that source's normalised text; then an independent entailment of
  the excerpt in context must equal the claimed relation, otherwise the finding is downgraded. The stored excerpt is the verified canonical string; `excerpt_fingerprint = Keccak256(excerpt)`.
- **Independence groups** (merge-only; label = smallest member id): sources merge when they share a registered publisher group (`PUBLISHER_GROUPS`) or registrable domain (`_registrable` with a partial suffix list), have
  identical or near-identical page text (word 5-gram containment of at least 80 % of the smaller page, deterministic hashing, bounded to 3000 words and 5 sources), share the same decision-bearing excerpt, or the model reports a shared origin.
  Page-level fingerprints are computed per node and only the resulting grouping is committed and compared.

## 8. Resolution rules

A source is *admissible* if `retrieval_status == OK` and its classification is `SUPPORTS` or `CONTRADICTS`. `S` / `C` count independent groups with an admissible `SUPPORTS` / `CONTRADICTS` source. In order:

| Rule | Condition | Result | Reason |
|---|---|---|---|
| R0 | a source is temporary and the attempt is not final | `RETRYABLE` (event stays `OPEN`) | 5 |
| R5 | proposition not assessable | `INCONCLUSIVE` | 4 |
| R3 | `S >= 1` and `C >= 1` | `INCONCLUSIVE` | 3 |
| R1 | `S >= 2` and `C == 0` | `CONFIRMED_TRUE` | 0 |
| R2 | `C >= 2` and `S == 0` | `CONFIRMED_FALSE` | 0 |
| R4 | no admissible source and some source unavailable | `INCONCLUSIVE` | 2 |
| R6 | anything else | `INCONCLUSIVE` | 1 |

Absence of evidence or an unreachable source never produces `CONFIRMED_FALSE`.

## 9. Consensus

`resolve_event` runs deterministic pre-checks (event exists and is `OPEN`; eligibility), copies the stored values to memory, then calls `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`.
Storage is written only afterwards, after `_check_structure` re-validates the accepted result and the `OPEN` state is re-checked.

**Leader result** (calldata-safe): `schema_version`, `criteria_version`, `event_id`, `proposition`, `evidence_findings` (one per source: `source_id`, `registered_url`, `registrable_domain`, `publisher_group`, `title`,
`publication_timestamp`, `update_timestamp`, `retrieval_status`, `source_type`, `classification`, `independence_group`, `excerpt`, `excerpt_fingerprint`, `source_commitment`), `independent_source_assessment`,
`proposed_outcome`, `outcome_reason`, `evidence_commitment`.

**Validator** returns `False` unless: the leader result is a `gl.vm.Return` (any `UserError`, `VMError` or unknown result is rejected); the deterministic structure gate passes (keys, types, enums, lengths, excerpt policy,
publisher/registrable identity recomputed from the registered URL, fingerprints and commitments recomputed, outcome consistent with its own findings); then, from its **own** fetch and analysis (any exception in them rejects),
`retrieval_status`, `classification`, `source_type`, `independence_group` and both dates are equal for every source; the leader's excerpts and titles occur in its own page text; its own entailment of **each of the leader's excerpts**
equals the leader's classification; and the proposed outcome and reason equal the outcome it derives itself (a terminal `INCONCLUSIVE` and a `RETRYABLE` are reproduced as rigorously as a conclusive result).

## 10. Data model

Contract storage: `next_event_id: u256` (starts at 1, overflow-guarded) and `events: TreeMap[u256, EventRecord]` (`u256` is a valid TreeMap key for linter rule `E018`).
`EventRecord`: `event_id u256`, `schema_version u32`, `criteria_version u32`, `submitter Address`, `proposition str`, `description str`, `event_start_timestamp u64`, `event_end_timestamp u64`,
`source_urls DynArray[str]`, `registration_timestamp u64`, `earliest_resolution_timestamp u64`, `lifecycle_status u8`, `outcome_reason u8`, `attempt_count u32`, `last_attempt_timestamp u64`, `last_attempt_reason u8`,
`parent_event_id u256`, `evidence DynArray[SourceEvidence]`, `evidence_commitment str`, `result_commitment str`, `resolution_timestamp u64`.
`SourceEvidence`: `source_id u8`, `registrable_domain str`, `publisher_group str`, `title str`, `publication_timestamp u64`, `update_timestamp u64`, `retrieval_status u8`, `source_type u8`, `classification u8`
(`1 SUPPORTS`, `2 CONTRADICTS`, `3 AMBIGUOUS`, `4 IRRELEVANT`, `5 UNAVAILABLE`), `independence_group u8`, `excerpt str`, `excerpt_fingerprint str`, `source_commitment str`.

## 11. Commitments, errors, identity

`Keccak256` from the SDK over canonical JSON (sorted keys, compact separators, ASCII-escaped). `source_commitment` covers every stored decision-bearing field; `evidence_commitment` the ordered list of source commitments;
`result_commitment` (computed by the contract after consensus) the versions, event id, proposition, interval, URLs, `evidence_commitment`, lifecycle and reason. A commitment proves integrity of the stored record, not publisher
authenticity or truth. Error prefixes: `[EXPECTED]` (invalid input or state) and `[LLM_ERROR]` (malformed model output; validators never agree, forcing leader rotation). Event ids are a stored monotonic counter, never derived from
collection size, wallet lists or ordering; every operation is keyed by `events[event_id]`; a finalised event can never be resolved again.

## 12. Project-defined limits and known limitations

All limits are project choices, not protocol limits: 2-5 sources; URL 12-500; proposition 20-300; description at most 1000; title at most 200; excerpt 40-300 characters and 6 words; 512 KiB raw and 20 000 text characters per source;
`list_event_ids` limit at most 20. Limitations: partial suffix list and static publisher registry; scripts without spaces cannot meet the 6-word rule; LLM judgements can agree wrongly; exact agreement between models may be rare enough to leave events `OPEN`;
real consensus, real LLM behaviour and WASM metering are unverified (see the remediation report, section 6).
