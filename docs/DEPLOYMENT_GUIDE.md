# TruthAnchor - Deployment and Verification Guide

> **Status:** the contract has **not** been deployed or verified in a real Studio or network. The independent audit verdict is
> **NOT READY - HIGH-PRIORITY DEFECTS FOUND** (see `TRUTHANCHOR_AUDIT_REPORT.md`). Do not deploy to a public network before finding
> F-01 is fixed. Use a local Studio or a disposable network to test.

## 1. What to deploy

`contracts/truth_anchor.py`, SDK generation A. The first two lines must stay exactly as they are and must be the first two lines of the
file you load:

```
# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Constructor: `__init__(self)` - **no arguments**. Leave the constructor argument list empty.

`variants/runner-kzybg95x/` holds an equivalent contract for the newer runner `kzybg95x...`. Use it only if your Studio serves that
runner; on a Studio that serves the v0.2.16 runner it fails to load ("Could not load contract schema").

## 2. Local verification (no network needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
genvm-lint download -v v0.2.16          # one-time download of the GenVM bundle that contains the runner
export GENVM_VERSION=v0.2.16            # always lint and test against that bundle

genvm-lint check contracts/truth_anchor.py --json
genvm-lint schema contracts/truth_anchor.py --output abi.json
pytest tests/direct -v
```

Expected: `ok: true`, `ctor_params: 0`, 7 methods; the schema constructor is `{"params": [], "kwparams": {}}`; the direct suite reports
`175 passed, 2 skipped, 11 xfailed` (each `xfailed` test is a documented audit finding, see `TRUTHANCHOR_AUDIT_TEST_MATRIX.md`).

`genvm-lint typecheck` currently exits 1 (audit finding F-09, a one-line annotation fix).

### Why the environment is pinned

- `genvm-linter` picks the newest cached GenVM bundle unless `GENVM_VERSION` is set; newer bundles do not contain runner `1jb45aa8...` and
  the linter reports `E101`.
- `genlayer-test` 0.29.2 uses the first bundle it finds in `~/.cache/gltest-direct`; `tests/direct/conftest.py` copies the v0.2.16 bundle
  there from the linter cache. If both caches are empty, run `genvm-lint download -v v0.2.16` first.
- Install `cloudpickle`; without it Direct Mode's pickling check silently does not run.

## 3. Manual verification in Studio (required, not yet done)

1. Load the **complete** file, starting at `# v0.2.16`. Confirm that the deploy panel shows **no constructor input fields**.
2. Deploy with an empty argument list.
3. Check the schema of the deployed address: constructor without parameters and these 7 methods: `register_event`, `resolve_event`,
   `get_event`, `get_event_status`, `get_event_count`, `list_event_ids`, `get_limits`.
4. Check the transaction receipt for successful **execution**, not only for an `ACCEPTED`/`FINALIZED` consensus status.
5. `register_event` with two public `https` URLs (separated by a space), read it with `get_event`, run `resolve_event`, read it again.

If Studio says "Could not load contract schema":

1. Make sure the whole file was pasted, including the two header lines.
2. Deploy the minimal `Storage` contract from the official examples in the same Studio. If that fails too, the problem is the environment.
3. Copy the full error text; without it the cause cannot be told apart.

## 4. Integration tests

```bash
TA_RUN_INTEGRATION=1 gltest tests/integration -v -s
# optional real-page smoke test:
TA_URL_1=https://... TA_URL_2=https://... TA_RUN_INTEGRATION=1 gltest tests/integration -v -s
```

They are skipped unless `TA_RUN_INTEGRATION=1`. They check deployment with `args=[]`, the initial state, registration and a resolution
smoke test. They were **not executed** during the audit.

## 5. What is not verified yet

- Loading and deployment of this exact file in a real Studio or network.
- Real multi-validator consensus, leader rotation and appeals.
- Behaviour on the GenVM WASM runner (Direct Mode runs on the host CPython): imports, closure serialisation, CPU/memory metering.
- Real LLM behaviour (agreement rate, JSON compliance, prompt injection).
- Real format of `gl.message_raw["datetime"]` on a network, and the web layer's redirect, timeout and size semantics.
