# TruthAnchor - Deployment and Verification Guide

> **Status:** the contract has **not** been deployed or verified on a real Studio or network. Use a local Studio (`localnet`) or a disposable
> network first. See `TRUTHANCHOR_DEPLOYMENT_VERIFICATION.md` for exactly what was verified and `TRUTHANCHOR_REMEDIATION_REPORT.md` (section 6) for what was not.

## 1. What to deploy

`contracts/truth_anchor.py`, SDK generation A. The first two lines must stay exactly as they are and be the first two lines of the file you load:

```
# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Constructor: `__init__(self)` - **no arguments**; `deploy/constructor_args.json` is `[]`. There is no other deployable source in the repository
(the old copy for runner `kzybg95x...` was removed; it did not load on a v0.2.16 Studio).

## 2. Local verification (no network)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
genvm-lint download -v v0.2.16          # one-time download of the GenVM bundle that contains the runner
export GENVM_VERSION=v0.2.16            # always lint and test against that bundle

genvm-lint check contracts/truth_anchor.py --json
genvm-lint typecheck contracts/truth_anchor.py
python deploy/verify_deployment.py      # 18 consistency checks, no network
pytest tests/direct -v                  # 381 tests
python tools/mutation_check.py          # 21 mutants, all must be killed
```

### Why the environment is pinned

- `genvm-linter` picks the newest cached GenVM bundle unless `GENVM_VERSION` is set; newer bundles do not contain runner `1jb45aa8...` and the linter reports `E101`.
- `genlayer-test` 0.29.2 uses the first bundle found in `~/.cache/gltest-direct`; `tests/direct/conftest.py` copies the v0.2.16 bundle there from the linter cache.
- Install `cloudpickle`; without it Direct Mode's pickling check silently does not run.
- `genlayer-test` 0.29.2 `warp()` does not update `gl.message_raw["datetime"]` after deployment; the tests use `set_time` in `tests/direct/helpers.py`.

## 3. Deploying with the guarded script

```bash
CONFIRM_DEPLOY=yes [NETWORK=localnet|studionet|testnet-asimov|testnet-bradbury] deploy/deploy.sh
```

The script first runs `deploy/verify_deployment.py` and aborts if the source, header, constructor, ABI or manifest disagree; it refuses to run without `CONFIRM_DEPLOY=yes`;
the default network is `localnet`. It calls `genlayer network set <network>` and `genlayer deploy --contract contracts/truth_anchor.py` (CLI syntax verified against `genlayer` 0.39.2).
**It was not executed against a real CLI during the remediation.**

After an intentional contract change run `python deploy/verify_deployment.py --write` to refresh the manifest hashes and `abi.json`.

## 4. Manual verification in Studio (required, not yet done)

1. Load the **complete** file, starting at `# v0.2.16`. Confirm that the deploy panel shows **no constructor input fields**.
2. Deploy with an empty argument list.
3. Check the schema of the deployed address: constructor without parameters and the 7 methods listed in the README.
4. Check the receipt for successful **execution**, not only for an `ACCEPTED`/`FINALIZED` consensus status.
5. `register_event` with two public `https` URLs, read it with `get_event` (note `earliest_resolution_timestamp`), try `resolve_event` immediately (it must be rejected),
   wait until the eligibility time, then resolve and read it again. A `RETRYABLE` result with `attempt_count` increased means a source was temporarily unavailable.

If Studio says "Could not load contract schema": paste the whole file including the two header lines; deploy the minimal `Storage` example in the same Studio (if that
fails too, the environment is the problem); copy the full error text.

## 5. Integration tests

```bash
TA_RUN_INTEGRATION=1 gltest tests/integration -v -s
# optional real-page test (sleeps past the 600 s delay):
TA_URL_1=https://... TA_URL_2=https://... TA_WAIT_FOR_ELIGIBILITY=1 TA_RUN_INTEGRATION=1 gltest tests/integration -v -s
```

They are skipped unless `TA_RUN_INTEGRATION=1` and were **not executed** during the remediation.

## 6. What is not verified yet

- Loading and deployment of this exact file in a real Studio or network.
- Real multi-validator consensus, leader rotation and appeals.
- Behaviour on the GenVM WASM runner (Direct Mode runs on host CPython): CPU/memory metering and timeouts, real closure serialisation.
- Real LLM behaviour (agreement rate, JSON compliance, prompt-injection resistance).
- The real format of `gl.message_raw["datetime"]` on a network, and the web layer's redirect, timeout and size semantics.
