# TruthAnchor - API and Runner Compatibility

Companion to `TRUTHANCHOR_REMEDIATION_REPORT.md`. Contract: `contracts/truth_anchor.py`, SHA-256
`50fd280f9444069f4b19017da0f2482629c9a1f853e027c45bd5d341c67fc157` (criteria v2).

Rule used throughout: **the installed SDK source and the observed behaviour take precedence over remembered syntax and over documentation pages**, and every
discrepancy is reported instead of silently resolved. The project was not migrated to another SDK version.

## 1. Target SDK generation and runner

| Item | Value |
|---|---|
| Generation | **A** (the generation of the official boilerplate and of the operator's Studio) |
| Header, line 1 | `# v0.2.16` |
| Header, line 2 | `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| GenVM bundle containing that runner | `v0.2.16` |
| SDK library in that bundle | `py-lib-genlayer-std/11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v` |
| Python runtime of the runner | `cpython:1bk9g3zgym0rrpd9lk584cxfaa4rg0cz36w6xhzkqdj1m2p4xa9n` (WASM) |
| Syntax | `from genlayer import *`, `class TruthAnchor(gl.Contract)`, `@allow_storage @dataclass`, `gl.vm.run_nondet_unsafe`, `gl.message_raw` |

The two header lines must be the first two lines of the file. A mismatch between the syntax and the runner hash is the most common cause of "Could not load contract schema".
The runner `kzybg95x...` (SDK v0.4.0-rc1, another generation) does **not** load with the v0.2.16 bundle (`E101: runner ... not found`); the contract that targeted it was removed from this repository.

## 2. Standard-library modules used and runtime availability

Imports of the contract: `json`, `re`, `typing`, `dataclasses`, `datetime`, and `from genlayer import *`. The remediation removed `import html` and every regular expression from the markup path.
Presence of `json`, `re`, `datetime` (and `html`, no longer used) in the standard library of the runner's CPython was verified by listing the runtime `cpython:1bk9g3zg...` extracted from the v0.2.16 bundle
(`py/std/json`, `py/std/re`, `py/std/datetime.py`). **They were not executed on the WASM runtime**; Direct Mode runs on the host CPython. `re` is used only for bounded validation patterns (host, date, hex, token),
never for markup. No third-party library is used.

## 3. Tooling

| Tool | Version | Notes |
|---|---|---|
| `genvm-linter` | 0.11.0 (PyPI) | Run with `GENVM_VERSION=v0.2.16`; without it the newest cached bundle lacks the runner (`E101`). Rule `E018`: TreeMap keys must be `str, Address, u32, u256, i32, i256, bytes` (a fixed linter list), hence `u256` ids |
| `genlayer-test` | 0.29.2 | Uses the first bundle in `~/.cache/gltest-direct`; `tests/direct/conftest.py` seeds it from the linter cache. **`warp()` updates `datetime.now()` but not `gl.message_raw["datetime"]` after deployment** (the loader captures it at construction); tests use `set_time` in `tests/direct/helpers.py` |
| `cloudpickle` | 3.1.2 | Needed for Direct Mode's `check_pickling` |
| `genlayer` CLI | 0.39.2 (npm) | Installed only to read its help; `genlayer deploy --contract <path> [--rpc <url>] [--args <args...>]`, `genlayer network set <network>`, networks `localnet`, `studionet`, `testnet-asimov`, `testnet-bradbury` |
| Python / pytest | 3.12.3 / 9.2.0 | |

## 4. Actual API signatures used (verified in the installed SDK source of runner `1jb45aa8...`)

| API | Signature / type | Used for |
|---|---|---|
| `gl.Contract`, `@gl.public.view`, `@gl.public.write` | base class and decorators | contract, 5 views, 2 writes |
| `@allow_storage` + `@dataclass` | storage-enabled dataclass at module level | `SourceEvidence`, `EventRecord` |
| `TreeMap[K, V]`, `DynArray[T]` | `in`, `[]`, `get_or_insert_default`; `append`, `append_new_get`, iteration | storage |
| `u8`, `u32`, `u64`, `u256`, `Address` | sized integers (explicit constructors), `.as_hex` | storage |
| `gl.message.sender_address` | `Address` (immediate caller; `origin_address` also exists, `signer_address` and `sender_account` do not) | `submitter` |
| `gl.message_raw["datetime"]` | ISO-8601 `str` | deterministic transaction time (eligibility, timestamps) |
| `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` | `validator_fn(leaders_res)` receives `gl.vm.Return` / `gl.vm.UserError` / `gl.vm.VMError`; validator errors are **not** caught by the SDK | consensus |
| `gl.vm.Return` | has `.calldata` | success result (read only after `isinstance`) |
| `gl.vm.UserError` | `UserError(message=...)`, `.message` | all `[EXPECTED]` / `[LLM_ERROR]` errors |
| `gl.nondet.web.get(url)` | `Response(status: int, headers: dict[str, bytes], body: bytes \| None)` | page retrieval |
| `gl.nondet.exec_prompt(prompt, response_format="json")` | decoded JSON value | analysis and entailment calls |
| `Keccak256(data: bytes).digest()` | Keccak preset (1088, 512, 256), pure Python, exported by `genlayer` | commitments and excerpt fingerprints (`hashlib` is not used) |

Execution-time `hasattr` probes in Direct Mode confirmed: `gl.vm.UserError` exists, `gl.UserError` does **not**, `gl.vm.run_nondet_unsafe` exists, `gl.vm.run_nondet_default` and `gl.contract` do not.

## 5. Non-deterministic execution API

The contract uses `gl.vm.run_nondet_unsafe`, as the official *Equivalence Principle* and *Error Handling* pages recommend for custom leader/validator logic. Because this variant does not
catch validator errors, `validator_fn` fails closed on every path: a non-`Return` leader result returns `False`; the structure gate runs before any web/LLM call; the validator's own analysis is wrapped so that any exception returns `False`.
The installed SDK docstring still describes `run_nondet` (the sandboxed variant) as "the recommended API for custom non-deterministic execution"; that is a documentation-versus-SDK discrepancy (the earlier version of the contract used `run_nondet`).

## 6. Deprecated or incompatible APIs discovered

| API | Where it appears | Status in generation A |
|---|---|---|
| `gl.UserError` | *Error Handling* and *Web Access* examples | **Not exported**; use `gl.vm.UserError` |
| `response.status_code` | *Web Access* examples | **Does not exist**; the attribute is `Response.status` |
| `gl.message.sender_account` | a source cited earlier in the project | **Does not exist** |
| `gl.contract.Contract`, `gl.storage.*`, `gl.vm.run_nondet_default`, `gl.message.raw`, `UserError.data` | SDK `main` (generation B) | **Not available** (`UserError` uses `.message`) |
| `@gl.contract` and `gl.UserError` skeletons | operator's skills notes | Do not match this SDK |

## 7. Address API

`gl.message` is a `NamedTuple` with `contract_address`, `sender_address` (call initiator, i.e. the immediate caller), `origin_address` (entire transaction initiator), `value`, `chain_id`; `gl.message_raw` is a `TypedDict` with the same
address fields plus the transaction `datetime`. The contract records `sender_address` as `submitter` (for a contract-to-contract call this is the calling contract). No `Address(...)` conversions occur because no public method accepts an address.

## 8. Documentation consulted

- **Read in full (earlier phases):** *The Equivalence Principle*, *Prompt Injection*, *Storage Quick Reference*, *Web Access*, *Transaction Context*; `sdk.genlayer.com/main/_static/ai/api.txt` (generation B, partially); the official boilerplate.
- **Read in this remediation:** *Error Handling* (https://docs.genlayer.com/developers/intelligent-contracts/features/error-handling).
- **Source code verified directly:** the SDK for runner `1jb45aa8...` (`gl/vm.py`, `gl/nondet/web.py`, `gl/nondet/__init__.py`, `gl/__init__.py`, `_internal/msg.py`, `py/keccak.py`, storage modules), `genlayer-test` 0.29.2 Direct Mode (`vm.py`, `sdk_loader.py`), the stdlib listing of the runner's CPython, and the CLI help of `genlayer` 0.39.2.
- **NOT read (any claim about these pages is unverified):** *Testing Intelligent Contracts*; *GenLayer Test API* and its *Direct Mode* page; `full-documentation.txt`; *Non-determinism*; *Calling LLMs*; the Types pages (*Address*, *Primitive*, *Collection*, *Dataclasses*); *glsim*; the *GenVM Linter* page;
  Studio pages (Limitations, Troubleshooting); the `skills.genlayer.com` pages. For the APIs they describe, the installed SDK and `genlayer-test` source were the authority.
