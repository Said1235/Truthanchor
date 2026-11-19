# TruthAnchor - Deployment Verification

**No live deployment was performed.** Nothing was broadcast to StudioNet, Asimov, Bradbury, mainnet or any other network, and no transaction was
signed. `deploy/deploy.sh` was **not executed** against a real CLI; its commands were checked only against a recording shim (section 6).

## 1. Authoritative contract and deployment source

| Item | Value |
|---|---|
| Authoritative contract file | `contracts/truth_anchor.py` |
| Exact deployment source path | `contracts/truth_anchor.py` (the only path used by `deploy/deploy.sh`, `deploy/deployment.json` and the ABI generation) |
| SHA-256 | `50fd280f9444069f4b19017da0f2482629c9a1f853e027c45bd5d341c67fc157` |
| Header (first two lines) | `# v0.2.16` / `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| Other deployable sources | **None.** The stale copy `variants/runner-kzybg95x/` was removed from the working tree (it stays in git history and in tag `v0.1.0-audited-baseline`); `verify_deployment.py` scans the repository and fails if a second contract source (a `gl.Contract` subclass or a runner header outside `tests/`) exists. |

## 2. Constructor signature and input schema

- Signature: `def __init__(self):` - **0 parameters**; body `self.next_event_id = u256(1)`.
- Deployment inputs: `deploy/constructor_args.json` = `[]` (must match the signature; a non-empty list fails `constructor_args_match_signature`).
- Schema extracted by `genvm-lint schema`: `"ctor": {"params": [], "kwparams": {}}`.
- The constructor was not changed. The zero-argument constructor is a project requirement (permissionless registry, no owner, no event data at deployment); no
  argument was added or removed for convenience, and the 7 public method signatures are unchanged.

## 3. Generated ABI / schema status

`abi.json` was regenerated from the corrected source with the project's tooling and is **byte-identical** to the baseline's ABI
(the public interface did not change): SHA-256 `a09606d9d9156868206e50a77f3a041fc0ac7799ad2c2d6b2fa70101edbaef14`.

| Method | Kind | Parameters | Returns |
|---|---|---|---|
| `register_event` | write | `proposition:string, description:string, event_start_timestamp:int, event_end_timestamp:int, source_urls:string, parent_event_id:int` | `int` |
| `resolve_event` | write | `event_id:int` | `string` |
| `get_event` | view | `event_id:int` | `dict` |
| `get_event_status` | view | `event_id:int` | `string` |
| `get_event_count` | view | - | `int` |
| `list_event_ids` | view | `offset:int, limit:int` | `array` |
| `get_limits` | view | - | `dict` |

`resolve_event` may now return `"RETRYABLE"` (the event stays open) in addition to the three outcome names; the return type (`string`) is unchanged.

## 4. Network configuration

`deploy/deployment.json`:

- default network `localnet` (local simulator); allowed: `localnet`, `studionet`, `testnet-asimov`, `testnet-bradbury`. These names were read from `genlayer network list` of the installed CLI (version **0.39.2**).
- Any other network must be selected explicitly with `NETWORK=<name>`; testnets additionally need a funded account.
- Verified CLI syntax (from `genlayer deploy --help` and `genlayer network --help`): `genlayer network set <network>`; `genlayer deploy --contract <path> [--rpc <url>] [--args <args...>]`.
- `"live_deployment_performed": false`.

## 5. Static checks (executed, from the repository root, `GENVM_VERSION=v0.2.16`, `genvm-linter` 0.11.0)

| Command | Exit | Result |
|---|---|---|
| `genvm-lint check contracts/truth_anchor.py --json` | 0 | `ok: true`; lint passed 3; validate: `TruthAnchor`, 7 methods (5 view, 2 write), `ctor_params: 0` |
| `genvm-lint lint contracts/truth_anchor.py --json` | 0 | `ok: true`, `passed: 3`, no warnings |
| `genvm-lint validate contracts/truth_anchor.py --json` | 0 | `ok: true`, 7 methods, `ctor_params: 0` |
| `genvm-lint typecheck contracts/truth_anchor.py` | 0 | "No type errors found" (the baseline exited 1) |
| `genvm-lint schema contracts/truth_anchor.py --output <tmp>` | 0 | identical to the committed `abi.json` |
| `pytest tests/direct -q` | 0 | **381 passed**, 0 failed, 0 skipped |
| `python tools/mutation_check.py` | 0 | 21 of 21 mutants killed; contract restored byte-for-byte |
| `pytest tests/integration --collect-only` | 0 | 4 tests collected; **none executed** (no Studio) |

The linter emits none of the `E010` / `E014` warnings of the other SDK generation; the TreeMap key type `u256` satisfies rule `E018`.

## 6. Deployment consistency checks

`python deploy/verify_deployment.py` (no network): **18 PASS, 0 FAIL, 0 BLOCKED**.

| Check | Result |
|---|---|
| manifest parses; authoritative contract exists | PASS |
| single deployable source in the repository | PASS |
| contract SHA-256 equals the manifest | PASS |
| header and runner equal the manifest | PASS |
| constructor parameters (parsed from the source with `ast`) equal the manifest | PASS |
| constructor arguments file matches the signature | PASS |
| ABI SHA-256 equals the manifest; ABI constructor has no parameters; ABI methods equal the manifest | PASS |
| **ABI regenerated from the source equals the committed ABI** | PASS |
| deploy script uses only the authoritative path; runs the check first; requires explicit confirmation; takes arguments only from the args file | PASS |
| network configuration is known; manifest states no live deployment | PASS |

14 tests in `tests/direct/test_deployment_consistency.py` show that the check **cannot be bypassed accidentally**. On a temporary copy of the repository, each of
these is detected: a modified contract, a constructor change that alters the schema, a tampered ABI, a second deployable copy, constructor arguments that do not match
the signature, a deploy script pointing at another file, header/runner drift, and an unknown network. With the GenLayer CLI replaced by a recording shim:
without `CONFIRM_DEPLOY=yes` the script exits 1 and the CLI is **never** called; with it, the exact calls are `genlayer network set localnet` and
`genlayer deploy --contract contracts/truth_anchor.py` (no `--args`, because the constructor is empty); a contract changed after the manifest makes the script refuse; the network changes only when `NETWORK` is set explicitly.

## 7. Reproducibility

```bash
pip install -r requirements-dev.txt
genvm-lint download -v v0.2.16
export GENVM_VERSION=v0.2.16
python deploy/verify_deployment.py          # verify (add --write only after an intentional contract change)
pytest tests/direct -v
CONFIRM_DEPLOY=yes deploy/deploy.sh         # deliberately NOT run during the remediation
```

After any change to `contracts/truth_anchor.py`, run `python deploy/verify_deployment.py --write` to refresh `deploy/deployment.json` and `abi.json`
from the source; until then every check that compares the hash fails by design.

## 8. Not verified

- Loading and deploying this exact file on a real Studio or network, and the Studio's own schema extraction.
- Anything involving real validators, real LLMs or the GenVM WASM runner (see `TRUTHANCHOR_REMEDIATION_REPORT.md`, section 6).
- `genlayer deploy` itself: the CLI was installed only to read its help; no command that contacts a network was run.
