# TruthAnchor - Design Specification (criteria v1)

This document describes the design **as implemented** in `contracts/truth_anchor.py` (SDK generation A, runner
`py-genlayer:1jb45aa8...`, GenVM v0.2.16). It started as a design proposal that was reviewed and approved before implementation;
where the implementation differs from that proposal, the difference is listed in section 14. Known defects of the implementation are
tracked in `TRUTHANCHOR_AUDIT_REPORT.md`.

## 1. Purpose and scope

TruthAnchor is a permissionless, evidence-based oracle for factual claims about **completed** public events. A user registers a precise
proposition, a context description, the UTC interval in which the event occurred, and 2 to 5 public `https` URLs. The contract retrieves
the registered URLs, has an LLM classify the evidence into a closed schema, has validators re-derive and verify that classification
independently, applies deterministic rules, and stores a permanent result under the event's exact id.

It does **not**: predict the future, judge opinions, guarantee absolute truth, discover sources, or accept pasted text as evidence.
The user's text defines *what* is evaluated; it is never evidence. It has no owner, administrator, roles or resolution deadline.

Supported claims (MVP): objectively assessable propositions about completed public events, for example an official publication of a law,
an announced acquisition, a court ruling, an organisation's approval, or the result of a finished competition. A proposition that the
analysis judges vague, an opinion or a prediction resolves to `INCONCLUSIVE` (reason 4).

## 2. Outcomes and lifecycle

| `lifecycle_status` (u8) | Name | Terminal |
|---|---|---|
| 0 | `OPEN` | no |
| 1 | `RESOLVED_TRUE` (`CONFIRMED_TRUE`) | yes |
| 2 | `RESOLVED_FALSE` (`CONFIRMED_FALSE`) | yes |
| 3 | `INCONCLUSIVE` | yes |

- The only transition is `OPEN -> {1, 2, 3}`, in a single atomic transaction. There is no `RESOLVING` state: a failed resolution reverts
  and the event stays `OPEN`.
- A new investigation creates a **new** event linked by `parent_event_id`; nothing is overwritten.
- `final_outcome` is **not stored**; views derive it from `lifecycle_status` (storing both could produce contradictory states).

`outcome_reason` (u8): `0 NONE` (conclusive), `1 INSUFFICIENT_INDEPENDENT_SOURCES`, `2 SOURCES_UNAVAILABLE`, `3 CONTRADICTORY_EVIDENCE`,
`4 AMBIGUOUS_OR_NOT_ASSESSABLE`.

## 3. Roles and access

Anyone may register, read, request resolution of an `OPEN` event, and read results. The registering caller is recorded as `submitter`
(`gl.message.sender_address`, the immediate caller). The constructor takes **no arguments** (`def __init__(self):`), so the contract is
deployable with an empty argument list; all event data is supplied afterwards through public methods.

## 4. Source registration policy

`source_urls` is one `str` with 2 to 5 URLs separated by whitespace. Validation (each failure is `UserError("[EXPECTED] ...")`):

1. Whole string at most 2504 characters, checked before splitting; then split on whitespace.
2. Between 2 and 5 URLs.
3. Each URL 12 to 500 characters, printable ASCII only, no spaces or control characters.
4. Scheme `https://` only.
5. No credentials (`@`), no IP literals, no `localhost`, no `.local` / `.internal` / `.localhost` hosts, no IPv6 literals; valid port if present.
6. Duplicate detection on a normalised key (lower-case scheme and host, `www.` removed, default port removed, fragment removed, trailing `/` removed).

URLs are stored as registered and are **immutable**; `resolve_event` only reads the URLs stored under the event id.

## 5. Source independence

Each source gets an `independence_group` (u8). Rule: **merge-only**.

1. Sources with the same normalised host share a group.
2. The LLM may merge groups (syndicated copies, same originating publication) through `same_origin_as`, never split them.
3. The label of a group is the smallest `source_id` it contains; validators compare the resulting labels exactly.
4. There is no reputation score. `source_type` is a closed vocabulary (`UNKNOWN 0`, `OFFICIAL_PRIMARY 1`, `NEWS_SECONDARY 2`, `OTHER 3`).

Known limitation (audit F-06): grouping does not detect byte-identical pages on different hosts.

## 6. Data model

Module constants: `SCHEMA_VERSION = 1`, `CRITERIA_VERSION = 1`.

Contract storage: `next_event_id: u256` (starts at 1, overflow-guarded) and `events: TreeMap[u256, EventRecord]`.

`EventRecord` (`@allow_storage` dataclass): `event_id u256`, `schema_version u32`, `criteria_version u32`, `submitter Address`,
`proposition str`, `description str`, `event_start_timestamp u64`, `event_end_timestamp u64`, `source_urls DynArray[str]`,
`registration_timestamp u64`, `lifecycle_status u8`, `outcome_reason u8`, `parent_event_id u256` (0 = none),
`evidence DynArray[SourceEvidence]`, `evidence_commitment str` (64 hex), `result_commitment str` (64 hex), `resolution_timestamp u64`.

`SourceEvidence` (flat dataclass): `source_id u8`, `publisher_host str`, `title str`, `publication_timestamp u64`, `update_timestamp u64`,
`retrieval_status u8` (`0 OK`, `1 HTTP_ERROR`, `2 EMPTY_OR_UNREADABLE`, `3 FETCH_ERROR`), `source_type u8`,
`classification u8` (`1 SUPPORTS`, `2 CONTRADICTS`, `3 CONTEXT_ONLY`, `4 INSUFFICIENT`, `5 UNAVAILABLE`), `independence_group u8`,
`excerpt str`, `source_commitment str`.

Every instant is Unix seconds UTC (`u64`); no formatted or natural-language dates are stored. TreeMap keys are `u256` because the
linter's rule `E018` accepts only `str, Address, u32, u256, i32, i256, bytes`.

## 7. Public interface

| Method | Kind | Parameters | Returns |
|---|---|---|---|
| `register_event` | write | `proposition: str, description: str, event_start_timestamp: u64, event_end_timestamp: u64, source_urls: str, parent_event_id: u256` | event id |
| `resolve_event` | write | `event_id: u256` | outcome name |
| `get_event` | view | `event_id: u256` | `dict` (full record, derived `final_outcome`) |
| `get_event_status` | view | `event_id: u256` | lifecycle name |
| `get_event_count` | view | none | count |
| `list_event_ids` | view | `offset: u256, limit: u256` (limit at most 20) | list of ids |
| `get_limits` | view | none | `dict` of project limits and versions |

Registration validation, in order: argument types; stripped proposition 20-300 characters; description at most 1000; start/end timestamps in
`0..2^64-1`; `start <= end`; `end <= transaction time` (only completed events); sources (section 4); optional parent (must exist, be
non-`OPEN`, and have exactly the same stored proposition). The proposition is stored stripped.

## 8. Resolution algorithm

`resolve_event(event_id)`:

1. Deterministic pre-checks: event exists and is `OPEN`. Copy the stored proposition, description, interval and URL list to memory; read the
   transaction time from `gl.message_raw["datetime"]`.
2. `gl.vm.run_nondet(leader_fn, validator_fn, compare_user_errors=...)`.
3. After consensus: re-validate the accepted result deterministically against the registered data, re-check that the event is still `OPEN`,
   then write evidence, commitments, lifecycle, reason and timestamp in one operation. Nothing is written before consensus completes.

**Leader (`_analyze`).** For each registered URL (at most 5): `gl.nondet.web.get`. A non-2xx status, an empty or unreadable body or any
exception becomes `UNAVAILABLE` - **never** evidence of falsity. Readable bodies are stripped of markup, normalised (casefold, whitespace
collapsed, typographic quotes mapped) and truncated to 12 000 characters. One prompt asks for a closed-vocabulary JSON classification per
source (`SUPPORTS`, `CONTRADICTS`, `CONTEXT_ONLY`, `INSUFFICIENT`; source type; verbatim excerpt up to 300 characters; title; dates;
`same_origin_as` links) and a `proposition_assessable` flag; source text is wrapped in delimiters and labelled untrusted data. The output is
validated defensively (`[LLM_ERROR]` on any violation). Deterministic post-processing: a `SUPPORTS`/`CONTRADICTS` classification without an
excerpt found in that source's text degrades to `INSUFFICIENT`; a non-assessable proposition forces every readable source to `INSUFFICIENT`.

**Leader result schema** (calldata-safe): `schema_version`, `criteria_version`, `event_id`, `proposition`, `evidence_findings` (exactly one
finding per registered source with `source_id`, `registered_url`, `publisher_host`, `title`, `publication_timestamp`, `update_timestamp`,
`retrieval_status`, `source_type`, `classification`, `independence_group`, `excerpt`, `source_commitment`),
`independent_source_assessment` (`groups`, `independent_supporting_groups`, `independent_contradicting_groups`), `proposed_outcome`,
`outcome_reason`, `evidence_commitment`. The LLM's free-text explanation is deliberately **not** part of the consensus result.

**Validator.** Rejects (returns `False`) unless all of the following hold:

1. The leader result is a `gl.vm.Return`; only then is `.calldata` read. A leader error is reproduced and compared (`[LLM_ERROR]` never agrees).
2. Exact structure: key sets, types, enums, lengths, source count equals the registered count, ids consecutive.
3. Bound to the registered data: `event_id`, `proposition`, versions, every URL, and the publisher host recomputed from the URL.
4. All commitments recomputed with Keccak256.
5. The validator independently fetches the same URLs and re-runs the same analysis; per source it requires exact equality of
   `retrieval_status`, `classification`, `source_type`, `independence_group`, `publication_timestamp` and `update_timestamp`.
6. The leader's excerpts and titles must appear in the validator's own page text.
7. `proposed_outcome` and `outcome_reason` equal the outcome the validator derives from its own findings (so a terminal `INCONCLUSIVE` is
   reproduced as rigorously as a conclusive result).

**Deterministic resolution rules.** A source is *admissible* if `retrieval_status == OK` and its classification is `SUPPORTS` or
`CONTRADICTS`. Let `S` / `C` be the number of independent groups with an admissible `SUPPORTS` / `CONTRADICTS` source. In order:

| Rule | Condition | Result | Reason |
|---|---|---|---|
| R5 | proposition not assessable | `INCONCLUSIVE` | 4 |
| R3 | `S >= 1` and `C >= 1` | `INCONCLUSIVE` | 3 |
| R1 | `S >= 2` and `C == 0` | `CONFIRMED_TRUE` | 0 |
| R2 | `C >= 2` and `S == 0` | `CONFIRMED_FALSE` | 0 |
| R4 | no admissible source and some source unavailable | `INCONCLUSIVE` | 2 |
| R6 | anything else | `INCONCLUSIVE` | 1 |

Absence of evidence or an unreachable source never produces `CONFIRMED_FALSE`.

## 9. Commitments

`Keccak256` from the SDK (pure Python; `hashlib` is not used) over canonical JSON (sorted keys, compact separators, ASCII-escaped).
`source_commitment` covers: schema version, event id, source id, registered URL, publisher host, normalised excerpt, classification,
retrieval status and both timestamps. `evidence_commitment` covers the ordered list of source commitments. `result_commitment`, computed by
the contract after consensus, covers: schema and criteria versions, event id, proposition, event interval, registered URL list,
`evidence_commitment`, lifecycle and reason. A commitment proves integrity of the stored record; it does not prove publisher authenticity or
truth. (Audit F-07: `title`, `source_type` and `independence_group` are not committed.)

## 10. Error policy

Prefixes implemented: `[EXPECTED]` (invalid input or state) and `[LLM_ERROR]` (malformed model output; validators never agree, which forces
leader rotation). The `[EXTERNAL]` / `[TRANSIENT]` classes of the official error pattern are **not** used (see audit finding F-04). A failed HTTP request is `UNAVAILABLE`, not falsity; a malformed LLM response is not a resolution; validator disagreement
never stores the leader's result; a failed transaction leaves no partial state. An accepted `INCONCLUSIVE` is a factual result and is
distinct from a failed execution or a consensus failure.

## 11. Event identity and concurrency

`event_id` is a stored monotonic counter, never derived from collection size, wallet lists, "latest" records or transaction order. Every
operation is keyed by `events[event_id]`; resolving one event cannot write to another; double resolution is rejected before and after the
non-deterministic block.

## 12. Project-defined limits (not protocol limits)

2-5 sources; URL 12-500 characters; `source_urls` at most 2504 characters; proposition 20-300; description at most 1000; title at most
200; excerpt at most 300; at most 300 000 bytes of body and 12 000 characters of text per source; `list_event_ids` limit at most 20;
ids below `2^256 - 1`. No protocol limits for calldata, storage, gas, time or memory were found in the documentation read; the limits above
are project choices.

## 13. Test strategy

Direct Mode (`genlayer-test` 0.29.2) with mocked web and LLM: deterministic rules, validation, identity, forged-result rejection
(including internally consistent forgeries), failure handling, and a mutation check of the validator. Integration tests
(`tests/integration`, `gltest`) cover empty-argument deployment and the register/resolve flow against a real Studio or network and are
**not executed** in the build environment. Direct Mode does not prove real multi-validator consensus.

## 14. Differences from the original proposal

| Topic | Original proposal | Implementation |
|---|---|---|
| SDK generation | B (`kzybg95x...`) | **A** (`1jb45aa8...`); B was found not to load on a v0.2.16 Studio and is kept only under `variants/` |
| Event id type | `u64` | `u256` (linter rule `E018` on TreeMap keys) |
| Non-deterministic API | `run_nondet_default` | `run_nondet` (generation A equivalent) |
| Body size | not bounded | at most 300 000 bytes per source (`MAX_BODY_BYTES`) |
| `description` | unspecified | stored as given; only the proposition is stripped |
| Excerpts | stored for all findings | stored only for `SUPPORTS` / `CONTRADICTS` |
