# TruthAnchor - Security Test Matrix (remediation)

Generated from the real pytest JUnit output of the final run of the complete direct suite (`pytest tests/direct`: 381 passed, 0 failed, 0 skipped).

- Contract under test: `contracts/truth_anchor.py`, SHA-256 `50fd280f9444069f4b19017da0f2482629c9a1f853e027c45bd5d341c67fc157`.
- Environment: GenVM v0.2.16 bundle (runner `py-genlayer:1jb45aa8...`), `genlayer-test` 0.29.2, `genvm-linter` 0.11.0, Python 3.12.3, `cloudpickle` 3.1.2 (pickling check active), `strict_mocks` enabled.
- **Direct Mode proves contract logic against mocked web and LLM calls.** It does not prove real multi-validator consensus, runner-level metering, real LLM behaviour or Studio schema loading; those remain NOT RUN (see the remediation report).
- Status values: PASS (executed and passed), FAIL, NOT RUN, N/A. BLOCKED does not occur in this run.

## Mandatory regression cases (task section 6)

| ID | Test | Attack or simulated condition | Expected behaviour | Actual result | Tests (file :: name, number of cases) | Evidence before the fix |
|---|---|---|---|---|---|---|
| S01 | Hostile 300 KiB HTML | 19 hostile shapes (angle-bracket floods, repeated incomplete tags, unclosed comments, 300 KiB quoted attribute, quote/delimiter mixes, malformed nesting, sparse tags, large script/style, entity floods) at 75, 150 and 300 KiB through the production extraction path | Work counter <= HTML_WORK_FACTOR (5) x input length for every shape and size; ratio constant across sizes (measured worst case 4.0); doubling the input does not quadruple the work; output never larger than input | **PASS** (81 cases) | `test_html_processing.py` :: `test_work_is_linear_on_hostile_input`, `test_doubling_input_does_not_quadruple_work`, `test_hostile_300kib_completes_quickly_wall_clock_supplement`, `test_work_bound_is_asserted_against_a_documented_constant` (+3 more) | Baseline regexes needed 33.5 s (`<script ` flood) and 45.2 s (`<` flood) for 300 KiB; baseline test FND01 xfail |
| S02 | Oversized HTML | Raw body above MAX_RAW_BYTES (512 KiB) that strips to a small text; extracted text above MAX_TEXT_CHARS (20 000); page exactly at the raw limit; 300 KiB page | Rejected as OVERSIZED without parsing past the limit; never evidence; exact-limit and 300 KiB pages are processed | **PASS** (5 cases) | `test_html_processing.py` :: `test_oversized_raw_body_is_rejected_and_never_evidence`, `test_oversized_extracted_text_is_rejected_and_never_evidence`, `test_300kib_page_is_not_oversized_at_the_raw_limit`, `test_raw_size_limit_is_enforced_independently_of_the_extracted_text_size` (+1 more) | Baseline capped at 300 000 bytes (below 300 KiB) and processed the truncated prefix as evidence |
| S03 | Prompt injection (caller) | 8 hostile propositions (instruction overrides, fake SYSTEM lines, JSON-shaped instructions, chat-template tokens, bidi controls) registered by a caller; hostile description and URL | Trusted prompt text identical for any caller input; no line can be added; description and URLs never reach the prompt; no public method accepts prompt/policy text | **PASS** (13 cases) | `test_prompt_injection.py` :: `test_trusted_text_is_identical_for_any_caller_input`, `test_entailment_prompt_has_the_same_property`, `test_caller_injection_end_to_end_keeps_the_trusted_prompt`, `test_description_never_reaches_the_prompt` (+2 more) | Baseline tests E04, E05, E06 xfail: proposition, description and URL were concatenated into the prompt |
| S04 | Delimiter injection | Proposition and page text containing the real delimiters, `DATA:` lines, `</DATA>`, closing/reopening JSON, fake system messages, hostile Unicode | All untrusted text stays inside one escaped JSON line (round-trips verbatim); prompt is ASCII; a model that obeys the injection still cannot finalise without a real quotation | **PASS** (12 cases) | `test_prompt_injection.py` :: `test_untrusted_strings_round_trip_exactly_inside_the_json_data`, `test_prompt_is_ascii_so_hostile_unicode_cannot_reach_the_model_raw`, `test_page_injection_stays_inside_json_and_is_lowercased_data`, `test_a_fooled_model_still_cannot_finalise_without_real_evidence` (+1 more) | Baseline delimiters were plain text: description/URL could spoof them (E04, E06) |
| S05 | Irrelevant excerpt | Trivial `the`; one long token; short with anchors; navigation; cookie notice; site description; unrelated paragraph; five words; keyword-stuffed irrelevant sentence; negated/rumour context; conflicting entailment | Not counted as support or contradiction; rejected excerpts are not stored; semantic entailment in context is the gate beyond the lexical filter | **PASS** (18 cases) | `test_evidence_and_independence.py` :: `test_B2_trivial_or_unanchored_excerpt_is_not_corroboration`, `test_B2_keyword_overlap_alone_is_not_proof_of_relevance`, `test_B2_keyword_overlap_passes_the_lexical_filter_so_the_semantic_step_is_the_real_gate`, `test_B2_entailment_that_does_not_confirm_the_claimed_relation_downgrades_it` (+5 more) | Baseline tests FND02/FND02b xfail: any substring, even `the`, was accepted |
| S06 | Duplicate pages across hosts | Byte-identical pages on two domains; same article with different chrome; same excerpt through different pages; one real source plus a mirror; five large near-copies | Counted as one content source (one independence group); duplicate kept as provenance; pairwise work bounded | **PASS** (6 cases) | `test_evidence_and_independence.py` :: `test_B4_identical_content_on_different_domains_is_one_source`, `test_B4_near_identical_content_with_different_site_chrome_is_one_source`, `test_B4_same_decision_excerpt_through_different_pages_counts_once`, `test_B5_a_duplicate_does_not_rescue_a_single_real_source` (+2 more) | Baseline test D04 xfail: identical content on different hosts counted as independent |
| S07 | Same publisher, multiple hosts | news.example.org + www.example.org; a/b.example.org; bbc.com + bbc.co.uk; shared hosting tenants; multi-label suffixes | One registered publisher group does not corroborate itself; unrelated tenants of a shared suffix remain independent; identities derive only from registered URLs and static tables | **PASS** (19 cases) | `test_evidence_and_independence.py`, `test_helpers_and_flow.py` :: `test_B3_two_hostnames_of_one_registered_domain_are_one_publisher`, `test_B3_subdomains_of_the_same_domain_are_one_publisher`, `test_B3_registered_publisher_group_spans_different_domains`, `test_B3_shared_hosting_tenants_are_not_one_publisher` (+5 more) | Baseline grouped by exact host only |
| S08 | All sources return 5xx | Every source returns 500/502/503/504/599 (also 429, 408, 425, 404, empty 200) | RETRYABLE: event stays OPEN; no outcome, no finalization timestamp, no commitments; attempt recorded; still resolvable | **PASS** (12 cases) | `test_lifecycle_retry.py` :: `test_C7_all_sources_temporarily_failing_leave_the_event_open_and_retryable`, `test_C8_all_sources_5xx_is_not_resolved_false_and_not_inconclusive` | Baseline test FND04 xfail: all-5xx became a terminal INCONCLUSIVE |
| S09 | All sources time out | The web layer raises TimeoutError / ConnectionError / OSError / unknown exceptions for every source | RETRYABLE; unknown exceptions fail closed as retryable; nothing finalised | **PASS** (5 cases) | `test_lifecycle_retry.py` :: `test_C9_all_sources_timing_out_or_failing_to_connect_leave_the_event_open`, `test_C10_unknown_web_exceptions_fail_closed_as_retryable` | Baseline swallowed exceptions into UNAVAILABLE and finalised |
| S10 | Immediate third-party resolution | A caller other than the creator resolves right after registration, at 0 s, 599 s, and with the settlement delay after a recent event end | Reverts `not yet eligible`; no state change for any caller; allowed from the earliest timestamp for every caller; eligibility uses the transaction time only | **PASS** (6 cases) | `test_lifecycle_retry.py` :: `test_C1_resolution_before_the_eligibility_time_is_rejected_without_any_state_change`, `test_C2_immediate_third_party_resolution_does_not_finalise`, `test_C3_eligibility_is_exactly_at_the_earliest_timestamp`, `test_C4_settlement_delay_after_event_end_postpones_eligibility` (+2 more) | Baseline test FND05: a third party finalised a terminal INCONCLUSIVE immediately |
| S11 | Valid independent corroboration | Two or three independent publishers with relevant, entailed excerpts after the eligibility time | Correct outcome finalised after consensus with evidence, commitments and timestamp | **PASS** (4 cases) | `test_evidence_and_independence.py` :: `test_B3_shared_hosting_tenants_are_not_one_publisher`, `test_B3_multi_label_public_suffix_keeps_different_owners_apart`, `test_B5_corroboration_counts_independent_groups_not_urls`, `test_B5_valid_independent_corroboration_after_eligibility_is_finalised` | - |
| S12 | Contradictory evidence | One supporting and one contradicting independent source | INCONCLUSIVE (reason 3) with both findings and both excerpts preserved; no leader-only decision | **PASS** (1 cases) | `test_evidence_and_independence.py` :: `test_B2_contradictory_evidence_stays_visible_and_blocks_a_verdict` | - |
| S13 | Missing evidence | Sources readable but irrelevant or ambiguous; proposition not assessable | INCONCLUSIVE, never CONFIRMED_FALSE (also exhaustively over class combinations) | **PASS** (3 cases) | `test_evidence_and_independence.py`, `test_validator_adversarial.py` :: `test_B2_missing_evidence_is_never_a_false_conclusion`, `test_B2_proposition_not_assessable_is_inconclusive`, `test_absence_of_evidence_never_yields_false_or_true` | - |
| S14 | Retry after temporary failure | Sources fail temporarily, then recover in a later transaction; closure condition after 3 attempts and 24 h | Later eligible attempt resolves correctly (history of the attempt kept); closure only when BOTH conditions hold; at closure remaining evidence decides | **PASS** (5 cases) | `test_lifecycle_retry.py` :: `test_C13_retry_after_temporary_failure_resolves_correctly`, `test_C14_temporary_failure_that_recovers_into_missing_evidence_is_inconclusive_not_false`, `test_C15_closure_needs_both_the_attempts_and_the_window`, `test_C16_window_alone_without_enough_attempts_does_not_close` (+1 more) | - |
| S15 | Repeated resolution | Resolve again after a terminal result, by the creator and a third party, with now-contradicting pages | Reverts `not open`; the stored historical outcome is not overwritten; a re-investigation is a new linked event | **PASS** (3 cases) | `test_lifecycle_retry.py` :: `test_C20_repeated_resolution_does_not_overwrite_a_finalised_event`, `test_C21_a_retryable_attempt_never_overwrites_or_creates_a_result`, `test_C22_inconclusive_terminal_is_overwritten_only_by_a_new_linked_event` | - |

## Additional boundary and failure cases

| ID | Case | Condition | Expected behaviour | Actual result | Tests |
|---|---|---|---|---|---|
| A01 | Malformed HTML | Unterminated tags/comments/scripts, lone angle brackets, nested malformed markup | Only the unterminated tail is dropped; lone `<` is text; no rescans | **PASS** (7 cases) | `test_work_is_linear_on_hostile_input`, `test_strips_tags_scripts_styles_and_comments`, `test_unterminated_markup_drops_only_the_unterminated_tail` (+2) |
| A02 | Empty pages | Empty and whitespace-only bodies | Incomplete response: retryable, never evidence | **PASS** (3 cases) | `test_empty_and_whitespace_pages_are_incomplete_not_evidence`, `test_C7_all_sources_temporarily_failing_leave_the_event_open_and_retryable` |
| A03 | Script/style content | Large script/style blocks, upper-case tags, `<scripts>` look-alike | Removed (or kept when not a script tag); linear | **PASS** (7 cases) | `test_work_is_linear_on_hostile_input`, `test_strips_tags_scripts_styles_and_comments` |
| A04 | Unusual whitespace and hostile Unicode | NBSP, zero-width, bidi controls, BOM, control characters | Normalised away deterministically | **PASS** (1 cases) | `test_unusual_whitespace_and_hostile_unicode_are_normalised` |
| A05 | Entity handling | Named/numeric/hex entities, invalid, oversized, floods, entity-encoded markup | Decoded once, no recursion, no re-parsing, output never larger than input | **PASS** (14 cases) | `test_work_is_linear_on_hostile_input`, `test_entities_are_decoded_once_without_recursion`, `test_entity_decoded_markup_is_not_reparsed` |
| A06 | Missing or foreign quotations | Excerpt absent from the page; excerpt from another source; exact reproduction check | Rejected / bound to its own source; stored excerpt occurs verbatim in the normalised page | **PASS** (3 cases) | `test_B2_excerpt_must_exist_in_the_page_text`, `test_B2_excerpt_from_another_source_is_rejected`, `test_B2_stored_excerpt_reproduces_exactly_from_the_normalised_page` |
| A07 | Invalid offsets | Offsets are not stored (page chrome shifts them between independent fetches) | N/A: exact quotation presence is verified instead and no offset fields exist | N/A (offsets not used) - verified by 1 cases | `test_B2_stored_excerpt_reproduces_exactly_from_the_normalised_page` |
| A08 | HTTP 429 and other temporary codes | 429, 408, 425, 404, empty 200 | Retryable | **PASS** (4 cases) | `test_C7_all_sources_temporarily_failing_leave_the_event_open_and_retryable` |
| A09 | Mixed successful and failed sources | Good source plus 5xx/429; permanent plus temporary | Not finalised while any source is temporarily failing | **PASS** (3 cases) | `test_C11_a_single_available_source_is_insufficient_when_the_others_are_down`, `test_C12_mixed_sources_with_one_temporary_failure_do_not_finalise_even_with_enough_evidence`, `test_C19_mixed_permanent_and_temporary_stays_retryable` |
| A10 | Malformed LLM JSON | Non-objects, wrong types, repeated/unknown ids, bad enums, malformed entailment | [LLM_ERROR]; nothing written; not a recorded attempt | **PASS** (11 cases) | `test_C24_llm_failure_is_not_a_factual_outcome_and_not_a_recorded_attempt`, `test_hostile_or_malformed_model_json_is_rejected_and_nothing_is_written`, `test_malformed_entailment_json_is_rejected` |
| A11 | Validator disagreement | Validator sees contradiction, support, independence, entailment, page change, source down | Leader result rejected; consensus failure changes nothing | **PASS** (15 cases) | `test_C23_validator_disagreement_or_consensus_failure_changes_nothing`, `test_C25_validator_side_temporary_failure_rejects_a_factual_leader_result`, `test_C26_leader_retryable_must_be_confirmed_by_the_validators_own_fetch` (+12) |
| A12 | Unknown exceptions | Unknown web/validator/leader errors | Fail closed (retryable / reject) | **PASS** (8 cases) | `test_C10_unknown_web_exceptions_fail_closed_as_retryable`, `test_leader_errors_are_never_accepted`, `test_validator_llm_failure_fails_closed` (+2) |
| A13 | Forged leader results | Internally consistent forgeries and tampering of every field | Rejected by independent re-derivation or the deterministic gate | **PASS** (45 cases) | `test_consistent_forgeries_are_rejected_by_independent_rederivation`, `test_forged_retrieval_status_is_rejected`, `test_forgeries_that_violate_the_evidence_policy_fail_the_deterministic_gate` (+6) |
| A14 | Permanent failures | 401/403/410/451/3xx/400 | Not retryable, INCONCLUSIVE reason 2, never a negative fact | **PASS** (7 cases) | `test_C18_permanent_failures_are_not_retryable_and_never_a_negative_fact` |
| A15 | Deployment consistency | Tampered contract/ABI/args/script/header/network, stale copy, CLI shim | Every mismatch detected; script never calls the CLI without confirmation; exact commands asserted | **PASS** (14 cases) | `test_the_committed_repository_is_consistent`, `test_modified_contract_is_detected`, `test_contract_change_that_alters_the_schema_is_detected_against_the_committed_abi` (+11) |
| A16 | Registration and identity | Rules, ids, parent links, views | Unchanged behaviour plus eligibility metadata | **PASS** (41 cases) | `test_ids_are_monotonic_and_failed_registrations_consume_none`, `test_two_callers_register_and_resolve_without_cross_assignment`, `test_interleaved_resolutions_keep_their_own_results` (+14) |

## Mutation check (defences are protected by tests)

`tools/mutation_check.py` weakens one defence at a time in a temporary copy of the contract and requires the suite to fail. The deployment-consistency tests are excluded from this run because any edit changes the contract hash. **21 of 21 mutants were KILLED, 0 survived** (M01-M21); the contract was restored byte-for-byte after each. A first run left M14 (raw size limit) alive because the oversize test also tripped the text-size limit; a test that separates the two (`test_raw_size_limit_is_enforced_independently_of_the_extracted_text_size`) was added and M14 is now killed.

| Mutant | Defence weakened |
|---|---|
| M01 KILLED | markup scanner rescans after a tag (quadratic/incorrect) |
| M02 KILLED | no minimum excerpt length |
| M03 KILLED | no minimum excerpt word count |
| M04 KILLED | no lexical anchoring of the excerpt to the proposition |
| M05 KILLED | entailment verdict ignored on the leader side |
| M06 KILLED | registered publisher/domain groups not merged |
| M07 KILLED | identical/near-identical page content not merged |
| M08 KILLED | identical excerpt through different pages not merged |
| M09 KILLED | no eligibility check on resolution |
| M10 KILLED | temporary failures finalise the event |
| M11 KILLED | validator accepts without independent comparison |
| M12 KILLED | closure condition removed |
| M13 KILLED | caller proposition appended outside the JSON data |
| M14 KILLED | oversized raw body is processed |
| M15 KILLED | validator ignores the entailment of the leader's excerpt |
| M16 KILLED | validator fails open on its own errors |
| M17 KILLED | validator accepts leader errors |
| M18 KILLED | a finalised event can be resolved again |
| M19 KILLED | oversized extracted text is accepted |
| M20 KILLED | 404 and incomplete responses are not retryable |
| M21 KILLED | web exceptions are not retryable |

## Totals by file (full suite)

| File | Passed | Failed | Skipped |
|---|---|---|---|
| `test_deployment_consistency.py` | 14 | 0 | 0 |
| `test_evidence_and_independence.py` | 37 | 0 | 0 |
| `test_helpers_and_flow.py` | 41 | 0 | 0 |
| `test_html_processing.py` | 94 | 0 | 0 |
| `test_lifecycle_retry.py` | 46 | 0 | 0 |
| `test_prompt_injection.py` | 35 | 0 | 0 |
| `test_registration.py` | 34 | 0 | 0 |
| `test_validator_adversarial.py` | 80 | 0 | 0 |
| **Total** | **381** | **0** | **0** |

Mandatory + additional rows: PASS 30, FAIL 0, NOT RUN 0.

## Not covered by this matrix

- Real multi-validator consensus, leader rotation and appeals (needs a Studio/network): **NOT RUN** (`tests/integration` collects 4 tests; none executed).
- Behaviour of real LLMs facing prompt injection or producing disagreeing classifications: **NOT RUN**.
- Execution on the GenVM WASM runner (imports, closure serialisation, CPU/memory metering): Direct Mode runs on host CPython.
- `genlayer-test` 0.29.2 `warp()` does not update `gl.message_raw["datetime"]` after deployment; the tests move the transaction clock through `set_time` in `tests/direct/helpers.py` (tooling limitation, not a contract defect).
