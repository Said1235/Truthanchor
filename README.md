# TruthAnchor

A permissionless, evidence-based **oracle Intelligent Contract for [GenLayer](https://www.genlayer.com)** that resolves factual claims
about real-world events that have already happened.

A user registers a precise proposition, the UTC interval in which the event occurred, and 2 to 5 public `https` sources. After a
registered eligibility time anyone can ask the contract to resolve it: the leader retrieves the registered pages and has an LLM classify
the evidence under a fixed, contract-owned policy; every validator re-fetches the same pages, re-derives the classification independently and
compares **every decision-bearing field**; the contract applies deterministic rules and stores a permanent record under the event's exact id.

> **Status: remediated pre-release, not deployed.**
> - A security review rejected the first version for three reasons; all three are fixed in this version (criteria v2): **linear, bounded HTML processing**,
>   **prompt-injection, trivial-excerpt and fake-corroboration defences**, and **retryable, eligibility-gated resolution**.
>   See [the remediation report](docs/TRUTHANCHOR_REMEDIATION_REPORT.md).
> - 381 direct tests pass; `genvm-lint` check/lint/validate/typecheck/schema are clean; 21 of 21 security mutants are killed; the deployment
>   consistency check passes (18/18).
> - **Not verified:** deployment on a real Studio or network, the integration tests, real multi-validator consensus, real LLM behaviour
>   (injection resistance, agreement rate) and execution on the GenVM WASM runner. **No live deployment was performed.**
>   Do not describe this as secure or production-ready until those are exercised; the residual risks are listed in the report.

## What it decides

| Outcome | Meaning |
|---|---|
| `CONFIRMED_TRUE` | At least two **independent** sources support the exact proposition with verified, relevant excerpts and none contradicts it |
| `CONFIRMED_FALSE` | At least two independent sources materially contradict it and none supports it |
| `INCONCLUSIVE` | Evidence insufficient, contradictory, ambiguous, permanently inaccessible, or the closure condition was reached |
| `RETRYABLE` (not a final state) | A source was temporarily unavailable; the event stays `OPEN` and can be resolved later |

Absence of evidence, an unreachable page, a failed LLM call or a consensus failure **never** becomes `CONFIRMED_FALSE`. Final results are never
overwritten; a re-investigation is a new linked event. TruthAnchor records an evidence-based resolution under explicit criteria; it does not guarantee absolute truth.

## How it stays safe

- **Bounded, linear HTML processing.** A single-pass scanner (no regular expressions) with a work counter; hostile 300 KiB pages are processed in about 0.2 s
  (the previous regexes needed 33-45 s); pages over 512 KiB raw or 20 000 extracted characters are `OVERSIZED` and never evidence.
- **Prompts are data, not instructions.** The policy is fixed in the contract; the proposition and page texts travel in one escaped JSON line; free-form
  descriptions and URLs never reach the model; model output is validated and never executed.
- **Evidence must mean something.** Sentence-sized, anchored to the proposition, verbatim in the page, and judged **in context** by an independent entailment
  step on both leader and validators.
- **Independence is derived, not claimed.** Registered publisher groups, registrable domains, identical or near-identical content and identical excerpts
  are merged deterministically; the model can only merge further.
- **Resolution is gated and retryable.** Not before `max(event_end + 1 h, registration + 10 min)` by the transaction time, for every caller; temporary failures
  (5xx, 429, 408, 404, timeouts, empty bodies) record an attempt and keep the event open, with a documented closure condition (3 attempts and 24 h).
- **Validators trust nothing.** They check `gl.vm.Return` before `.calldata`, recompute commitments, fetch the pages themselves, compare all decision fields,
  judge the leader's own excerpts, and fail closed on every error. Storage is written only after consensus and a second deterministic validation.

## Repository layout

```
contracts/truth_anchor.py               the Intelligent Contract (SDK generation A, runner 1jb45aa8..., GenVM v0.2.16)
abi.json                                extracted ABI (the public interface is unchanged from v0.1.0)
deploy/                                 deployment manifest, constructor arguments, guarded deploy script, consistency verifier
tests/direct/                           Direct Mode suite (genlayer-test 0.29.2): 381 tests
tests/integration/                      gltest integration tests (need a Studio/network; not executed yet)
tools/mutation_check.py                 weakens one defence at a time; the suite must fail (21 mutants)
docs/TRUTHANCHOR_REMEDIATION_REPORT.md        root causes, changes, proof and residual risks for the three review findings
docs/TRUTHANCHOR_SECURITY_TEST_MATRIX.md      every mandatory regression case with its actual result
docs/TRUTHANCHOR_DEPLOYMENT_VERIFICATION.md   source/deployment consistency and static checks
docs/TRUTHANCHOR_DESIGN_PROPOSAL.md           design specification (criteria v2)
docs/TRUTHANCHOR_API_COMPATIBILITY.md         SDK/runner compatibility, exact APIs, documentation discrepancies
docs/DEPLOYMENT_GUIDE.md                      how to verify locally and what to check on a real Studio
docs/TRUTHANCHOR_AUDIT_*.md                   independent audit of the BASELINE v0.1.0 (superseded; kept for traceability)
```

The reviewed baseline is the git tag `v0.1.0-audited-baseline`. A second, vulnerable contract copy for another runner that lived under `variants/` was
removed from the working tree (it remains in that tag) so that no stale deployable source exists.

## Contract interface

`__init__(self)` takes **no arguments**; all event data is supplied after deployment.

| Method | Kind | Parameters | Returns |
|---|---|---|---|
| `register_event` | write | `proposition: str, description: str, event_start_timestamp: u64, event_end_timestamp: u64, source_urls: str, parent_event_id: u256` | event id |
| `resolve_event` | write | `event_id: u256` | `CONFIRMED_TRUE`, `CONFIRMED_FALSE`, `INCONCLUSIVE` or `RETRYABLE` |
| `get_event` | view | `event_id: u256` | full record (`dict`) incl. eligibility and attempt metadata |
| `get_event_status` | view | `event_id: u256` | lifecycle name |
| `get_event_count` | view | - | number of events |
| `list_event_ids` | view | `offset: u256, limit: u256` | list of ids (limit at most 20) |
| `get_limits` | view | - | project limits and versions |

`source_urls` is one string with 2 to 5 `https` URLs separated by whitespace. Pass `parent_event_id = 0` for a new claim.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
genvm-lint download -v v0.2.16
export GENVM_VERSION=v0.2.16

genvm-lint check contracts/truth_anchor.py --json
genvm-lint typecheck contracts/truth_anchor.py
python deploy/verify_deployment.py
pytest tests/direct -v
python tools/mutation_check.py
```

Expected: `ok: true`, `ctor_params: 0`, `No type errors found`, `18 PASS, 0 FAIL`, `381 passed`, `survivors: none`.
The first two lines of the contract (`# v0.2.16` and the `Depends` line) select the runner; a mismatch with the Studio's runner is the most common cause
of "Could not load contract schema". See the [deployment guide](docs/DEPLOYMENT_GUIDE.md).

## Project limits and policy constants

All are **project-defined**, not GenLayer protocol limits: 2-5 sources; URL 12-500 characters; proposition 20-300; description up to 1000; raw body up to
512 KiB and extracted text up to 20 000 characters per source; excerpts 40-300 characters and at least 6 words; resolution delay 600 s after registration
and 3600 s after the event end; closure after 3 attempts and 24 h; `list_event_ids` limit up to 20.

## Limitations

- The submitter chooses the sources, so a result is only as trustworthy as those pages.
- The suffix list and publisher registry are partial seed lists compiled into the contract; paraphrased copies and unrelated-looking domains of one owner are not detected.
- Scripts written without spaces (e.g. Chinese, Japanese) cannot satisfy the 6-word excerpt rule and resolve conservatively to `INCONCLUSIVE`.
- Exact agreement between independent LLMs can fail often enough that an event stays `OPEN`; this is safe but unmeasured.
- A permanently flaky source keeps an event `OPEN` until the closure condition.
- Protocol-level limits (gas, time, memory, calldata, storage) were not found in the documentation read and are unverified.

## Documentation used

Official GenLayer documentation (Equivalence Principle, Error Handling, Prompt Injection, Storage reference, Web Access, Transaction Context), the official
project boilerplate and the SDK source of the target runner. Pages that were **not** read are listed in
[`docs/TRUTHANCHOR_API_COMPATIBILITY.md`](docs/TRUTHANCHOR_API_COMPATIBILITY.md).

## License

Not chosen yet. Add a `LICENSE` file before publishing.
