# TruthAnchor

A permissionless, evidence-based **oracle Intelligent Contract for [GenLayer](https://www.genlayer.com)** that resolves factual claims
about real-world events that have already happened.

A user registers a precise proposition, the UTC interval in which the event occurred, and 2 to 5 public `https` sources. Anyone can then
ask the contract to resolve it: the leader retrieves the registered pages and has an LLM classify the evidence into a closed schema; every
validator re-fetches the same pages, re-derives the classification independently and compares **every decision-bearing field**; the contract
applies deterministic rules and stores a permanent record under the event's exact id.

> **Status: pre-release, not production-ready.**
> - An independent audit found **1 HIGH, 6 MEDIUM, 3 LOW** findings and 5 informational notes. Verdict:
>   **NOT READY - HIGH-PRIORITY DEFECTS FOUND** ([audit report](docs/TRUTHANCHOR_AUDIT_REPORT.md)). The HIGH finding (F-01: quadratic HTML
>   stripping, about 40 s of CPU for a hostile 300 KB page) has a verified small fix that has **not** been applied yet.
> - The contract has **not been deployed** to a real Studio or network, and the integration tests have **not been executed**.
> - Direct-mode results (175 passed, 2 skipped, 11 expected failures = confirmed defects) use mocked web and LLM calls; they do not prove real
>   multi-validator consensus.

## What it decides

| Outcome | Meaning |
|---|---|
| `CONFIRMED_TRUE` | At least two **independent** sources support the exact proposition and none contradicts it |
| `CONFIRMED_FALSE` | At least two independent sources materially contradict it and none supports it |
| `INCONCLUSIVE` | Evidence insufficient, inaccessible, ambiguous or contradictory |

Absence of evidence, an unreachable page, a failed LLM call or a consensus failure **never** becomes `CONFIRMED_FALSE`. The lifecycle is
`OPEN -> RESOLVED_TRUE | RESOLVED_FALSE | INCONCLUSIVE`; results are terminal and never overwritten (a re-investigation is a new linked event).
TruthAnchor records an evidence-based resolution under explicit criteria; it does not guarantee absolute truth.

## Why the consensus design matters

The classic failure of LLM oracles is a validator that only checks "valid JSON, same outcome". TruthAnchor's validator does not trust the
leader's result:

- It only reads `.calldata` after confirming a successful `gl.vm.Return`.
- It re-fetches **all** registered URLs itself and re-runs the same analysis.
- It requires exact equality of retrieval status, classification, source type, independence group and dates for every source, and that the
  leader's quotations occur in its own copy of the page.
- It recomputes every commitment (Keccak256 over canonical JSON) and the outcome derived from its own findings, so a lazy or malicious leader
  cannot force even a terminal `INCONCLUSIVE`.
- The contract re-validates the accepted result deterministically and only then writes storage; nothing is written before consensus.

Fifteen explicit leader-versus-validator contradiction scenarios are tested and rejected, including forgeries with valid structure and valid
commitments. Replacing the validator with a naive structure-only check makes 13 adversarial tests fail.

## Repository layout

```
contracts/truth_anchor.py        the Intelligent Contract (SDK generation A, runner 1jb45aa8...)
tests/direct/                    Direct Mode suite (genlayer-test 0.29.2)
tests/integration/               gltest integration tests (need a Studio/network; not executed yet)
docs/TRUTHANCHOR_DESIGN_PROPOSAL.md     design specification as implemented
docs/TRUTHANCHOR_AUDIT_REPORT.md        independent audit report with findings and remediation proposals
docs/TRUTHANCHOR_AUDIT_TEST_MATRIX.md   every adversarial scenario, expected vs actual result
docs/TRUTHANCHOR_API_COMPATIBILITY.md   SDK/runner compatibility, exact APIs, documentation discrepancies
docs/DEPLOYMENT_GUIDE.md                local verification and manual Studio checklist
variants/runner-kzybg95x/        same logic for the newer runner kzybg95x... (NOT audited; does not load on a v0.2.16 Studio)
abi.json                         extracted ABI of the audited contract
```

## Contract interface

`__init__(self)` takes **no arguments**; all event data is supplied after deployment.

| Method | Kind | Parameters | Returns |
|---|---|---|---|
| `register_event` | write | `proposition: str, description: str, event_start_timestamp: u64, event_end_timestamp: u64, source_urls: str, parent_event_id: u256` | event id |
| `resolve_event` | write | `event_id: u256` | outcome name |
| `get_event` | view | `event_id: u256` | full record (`dict`) |
| `get_event_status` | view | `event_id: u256` | lifecycle name |
| `get_event_count` | view | - | number of events |
| `list_event_ids` | view | `offset: u256, limit: u256` | list of ids (limit at most 20) |
| `get_limits` | view | - | project limits and versions |

`source_urls` is a single string with 2 to 5 `https` URLs separated by whitespace. Pass `parent_event_id = 0` for a new claim.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
genvm-lint download -v v0.2.16
export GENVM_VERSION=v0.2.16

genvm-lint check contracts/truth_anchor.py --json
genvm-lint schema contracts/truth_anchor.py --output abi.json
pytest tests/direct -v
```

Expected: `ok: true`, `ctor_params: 0`, `175 passed, 2 skipped, 11 xfailed`. The 11 `xfailed` tests assert the *safe* behaviour for each
confirmed audit finding; when a finding is fixed its test flips to XPASS and strict mode asks you to remove the marker. See the
[deployment guide](docs/DEPLOYMENT_GUIDE.md) for the manual Studio checklist and why the toolchain is pinned.

The first two lines of the contract (`# v0.2.16` and the `Depends` line) select the runner. A mismatch between the runner and the syntax
generation is the most common cause of "Could not load contract schema".

## Known findings (summary)

| ID | Severity | Summary |
|---|---|---|
| F-01 | **HIGH** | HTML stripping regexes are quadratic (hostile 300 KB page ~ 40 s CPU per node, extrapolated) |
| F-02 | MEDIUM | Quotation guard accepts trivial or irrelevant excerpts |
| F-03 | MEDIUM | User text (proposition, description, URL) enters the LLM prompt unescaped |
| F-04 | MEDIUM | A transient outage of all sources becomes a terminal `INCONCLUSIVE` |
| F-05 | MEDIUM | Anyone can finalise a fresh event as `INCONCLUSIVE` before sources are published |
| F-06 | MEDIUM | Source independence is not deterministic (identical pages on different hosts) |
| F-07 | MEDIUM | Commitments omit `title`, `source_type`, `independence_group` |
| F-08, F-09, F-10 | LOW | Unverified dates; `typecheck` exit code; dead code |

Details, line numbers, reproducible tests and the smallest safe remediation for each are in the [audit report](docs/TRUTHANCHOR_AUDIT_REPORT.md).

## Project limits

All limits are **project-defined**, not GenLayer protocol limits: 2-5 sources, URL 12-500 characters, proposition 20-300, description up to
1000, up to 300 000 body bytes and 12 000 text characters per source, `list_event_ids` limit up to 20.

## Limitations

- The submitter chooses the sources, so a result is only as trustworthy as those pages.
- Source independence is host-based plus an LLM judgement; mirrors and subdomains of one organisation can still look independent.
- Exact agreement between independent LLMs may fail often enough that an event stays `OPEN`; this is safe but unmeasured.
- Protocol-level limits (gas, time, memory, calldata, storage) were not found in the documentation read and are unverified.

## Documentation used

Official GenLayer documentation (Equivalence Principle, Prompt Injection, Storage reference, Web Access, Transaction Context), the official
project boilerplate and the SDK source of the target runner. Pages that were **not** read are listed in
[`docs/TRUTHANCHOR_API_COMPATIBILITY.md`](docs/TRUTHANCHOR_API_COMPATIBILITY.md).

## License

Not chosen yet. Add a `LICENSE` file before publishing.
