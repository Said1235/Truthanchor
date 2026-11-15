# TruthAnchor - API and Runner Compatibility

Companion to `TRUTHANCHOR_AUDIT_REPORT.md`. Audited file: `contracts/truth_anchor.py`,
SHA-256 `6fdf243441b1fe025fa04485cf122e0df67221f3c717531bf9f87e3126ae3095`.

Rule used throughout: **the installed SDK source and the observed behaviour take precedence over remembered syntax and over
documentation pages**, and every discrepancy is reported instead of silently resolved.

## 1. Target SDK generation and runner

| Item | Value |
|---|---|
| Generation | **A** (the generation used by the official boilerplate and by the operator's Studio) |
| Header, line 1 | `# v0.2.16` |
| Header, line 2 | `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| GenVM bundle containing that runner | `v0.2.16` |
| SDK library in that bundle | `py-lib-genlayer-std/11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v` |
| Contract syntax | `from genlayer import *`, `class TruthAnchor(gl.Contract)`, `@allow_storage @dataclass`, `gl.vm.run_nondet`, `gl.message_raw` |

The two header lines must be the first two lines of the file. A mismatch between the syntax and the runner hash is the most
common cause of the Studio error "Could not load contract schema".

### Runner hashes seen during the engagement

| Runner `py-genlayer:` | Where it came from | Generation / syntax | Result |
|---|---|---|---|
| `1jb45aa8...09h6` | boilerplate `main`, operator's template, operator's skills notes | A | **Audit target.** `genvm-lint`: `ok`, `ctor_params: 0`; Direct Mode: all tests pass |
| `kzybg95x...z0` | `sdk.genlayer.com/main/_static/ai/api.txt` (SDK v0.4.0-rc1) | B (`import genlayer as gl`, `gl.contract.Contract`, `gl.storage.*`, `run_nondet_default`) | Validates with the genvm-manager bundle v0.6.0-rc15, but **does not load with the v0.2.16 bundle** (`E101: runner kz/ybg95x... not found`). Shipped separately under `variants/`, **not audited** |
| `1zr6nqk5...qvfwh` | GenVM v0.3.0-rc7 bundle | n/a | Not loadable by the installed linter; not a candidate |
| `5jycge4q...qng` | A stale message printed by a linter run with an older cache | n/a | Not present in the newer bundle; ignored |

## 2. Linter and test-framework compatibility

| Tool | Version used | Notes |
|---|---|---|
| `genvm-linter` | 0.11.0 (PyPI) | Must run with `GENVM_VERSION=v0.2.16`; without it the linter picks the newest cached bundle, which lacks runner `1jb45aa8...` (`E101`). Run `genvm-lint download -v v0.2.16` once |
| `genlayer-test` | 0.29.2 | Picks the first GenVM bundle found in `~/.cache/gltest-direct`; if none is cached it tries to download `latest` (a 404 at the time of the audit). `tests/direct/conftest.py` seeds that cache from the linter cache |
| `genlayer-test` 0.30.0rc2 | not used for this target | The operator's playbook reports that it cannot load generation-A contracts; this was **not re-tested** here |
| `cloudpickle` | 3.1.2 | Without it Direct Mode's `check_pickling` silently does not run |
| Linter rule `E018` | observed | TreeMap keys must be one of `str, Address, u32, u256, i32, i256, bytes`; this is a fixed list in the linter, not derived from the SDK. `u64` keys were rejected, so ids are `u256` |
| Linter rules `E010` / `E014` | not triggered on this generation | They are false positives on generation B |

## 3. Actual API signatures used (generation A, verified in the installed SDK source)

| API | Signature / type | Used for | Verified by |
|---|---|---|---|
| `gl.Contract` | base class (exactly one per file) | `class TruthAnchor(gl.Contract)` | SDK source; linter |
| `@gl.public.view`, `@gl.public.write` | method decorators | 5 views, 2 writes | SDK source; schema output |
| `@allow_storage` + `@dataclass` | storage-enabled dataclass, declared at module level | `SourceEvidence`, `EventRecord` | SDK source; boilerplate `football_bets.py`; Direct Mode |
| `TreeMap[K, V]` | persistent map; `in`, `[]`, `get_or_insert_default(key)` | `events: TreeMap[u256, EventRecord]` | SDK source; tests |
| `DynArray[T]` | persistent array; `append`, `append_new_get()`, iteration | `source_urls`, `evidence` | SDK source; tests |
| `u8`, `u32`, `u64`, `u256` | sized integers; assigned with explicit constructors | all numeric storage | SDK source; linter |
| `Address` | `.as_hex` | `submitter` | SDK source; tests |
| `gl.message.sender_address` | `Address` (immediate caller) | `submitter` | SDK source (`gl/__init__.py`) |
| `gl.message_raw["datetime"]` | `str` (ISO-8601 transaction datetime) | registration and resolution timestamps | SDK source; Direct Mode. The real network format is unverified |
| `gl.vm.run_nondet(leader_fn, validator_fn, *, compare_user_errors=..., compare_vm_errors=...)` | sandboxed validator; if the leader returned `Return` the validator must return a bool | consensus | SDK source `gl/vm.py` |
| `gl.vm.Return` | has `.calldata` | success result | SDK source |
| `gl.vm.UserError` | `UserError(message=...)`, attribute `.message` | all `[EXPECTED]` / `[LLM_ERROR]` errors | SDK source; tests |
| `gl.nondet.web.get(url)` | returns `Response(status: int, headers: dict[str, bytes], body: bytes \| None)` | page retrieval | SDK source `gl/nondet/web.py` |
| `gl.nondet.exec_prompt(prompt, response_format="json")` | returns a decoded JSON value | classification | SDK source |
| `Keccak256(data: bytes).digest()` | Keccak preset (1088, 512, 256), pure Python; exported by `genlayer` | commitments | SDK source `py/keccak.py`; tests. **`hashlib` is not used** |

## 4. Non-deterministic execution API

- The contract uses `gl.vm.run_nondet` with a custom `compare_user_errors`.
- Official page (*The Equivalence Principle*, read in full) recommends `run_nondet_unsafe` and handling errors inside the validator for custom
  patterns, and describes `run_nondet` as used internally by the convenience functions.
- The installed SDK docstring for `run_nondet` says the opposite: "the recommended API for custom non-deterministic execution".
- **This is a documentation-versus-SDK discrepancy and is reported as finding F-11.** Behaviour demonstrated: a validator exception is never
  accepted silently; leader `UserError` results are compared via `compare_user_errors`; `[LLM_ERROR]` always disagrees.
- Semantics relied on (verified in `gl/vm.py`): if the leader returned `Return`, the validator function must return a bool; if the leader
  raised `UserError`, the validator function must reproduce a comparable error; the validator sandbox allows storage writes, so the validator
  code never writes.

## 5. Address API

Verified in the SDK source (`gl/__init__.py`, `_internal/msg.py`): `gl.message` is a `NamedTuple` with `contract_address`,
`sender_address` ("address of this call initiator", i.e. the immediate caller), `origin_address` ("entire transaction initiator"),
`value` and `chain_id`; `gl.message_raw` is a `TypedDict` with the same address fields plus the transaction `datetime`.
There is **no** `signer_address` and **no** `sender_account` in this generation.

The contract uses only `gl.message.sender_address` and records the *immediate caller* as `submitter` (finding F-14: for a
contract-to-contract call this is the calling contract, not the originating wallet; `origin_address` would identify the wallet).
No `Address(...)` conversions are performed because no public method accepts an address.

## 6. Storage API and limits

Storage follows the *Storage Quick Reference* (read in full): annotated class fields, `DynArray` / `TreeMap` with full generics, sized
integers, zero-initialised defaults, copy to memory before non-deterministic blocks (done manually for scalars and lists).
Protocol limits for calldata, storage size, gas, time and memory were not found in the pages read; all limits in the contract are
**project-defined**.

## 7. Deprecated or incompatible APIs discovered

| API | Where it appears | Status in generation A (this target) |
|---|---|---|
| `gl.UserError` | Web Access page examples | **Not exported**; use `gl.vm.UserError` |
| `response.status_code` | Web Access page examples | **Does not exist**; the attribute is `Response.status` |
| `gl.message.sender_account` | an unverified source cited during the project | **Does not exist** |
| `gl.contract.Contract`, `gl.storage.*`, `gl.vm.run_nondet_default`, `gl.message.raw` | SDK `main` (`api.txt`, generation B) | **Not available** in generation A (`gl.contract` and `run_nondet_default` were checked absent in the loaded SDK) |
| `UserError.data` | generation B | Generation A uses `.message` |
| `@gl.contract` and `gl.UserError` skeletons | operator's skills notes | Do not match this SDK |

## 8. Documentation consulted

**Read in full during the audit:** *The Equivalence Principle*, *Prompt Injection*, *Storage Quick Reference*.
**Read during the earlier design phase:** *Web Access*, *Transaction Context*, `sdk.genlayer.com/main/_static/ai/api.txt` (generation B, partially),
the official boilerplate (`CLAUDE.md`, contracts, tests, requirements) and the operator's playbook and skills notes.
**Source code verified directly:** the SDK for runner `1jb45aa8...` (`gl/vm.py`, `gl/nondet/web.py`, `gl/nondet/__init__.py`,
`gl/__init__.py`, `py/keccak.py`, storage modules), `genlayer-test` 0.29.2 Direct Mode (`vm.py`, `sdk_loader.py`).

**NOT read (any claim about these pages is unverified):** `full-documentation.txt`; *Non-determinism*; *Calling LLMs*; the Types pages
(*Address*, *Primitive*, *Collection*, *Dataclasses*); *Testing* and the *Direct Mode* page; *glsim*; the *GenVM Linter* page;
*Studio* pages (Limitations, Troubleshooting, Development Tips); the `skills.genlayer.com` site pages.
For the APIs those pages describe, the installed SDK source was used as the authority.

## 9. Variant B (not audited)

`variants/runner-kzybg95x/` contains the same logic for runner `kzybg95x...` (SDK v0.4.0-rc1): `import genlayer as gl`,
`gl.contract.Contract`, `gl.storage.*`, `run_nondet_default`, `gl.message.raw`, `u64` ids. It passes its own 128 direct tests with
`genlayer-test` 0.30.0rc2 and `GENVM_VERSION=v0.6.0-rc15`, and it **fails to load on a Studio that serves the v0.2.16 runner**. It was
not part of this audit and the findings of the audit report apply to it by inheritance (same logic) but were not re-verified there.
