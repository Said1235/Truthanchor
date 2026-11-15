# Variant for runner kzybg95x (SDK v0.4.0-rc1) - NOT AUDITED

Same logic as the audited contract in ../../contracts/truth_anchor.py, written for the newer SDK generation
(import genlayer as gl, gl.contract.Contract, gl.storage.*, gl.vm.run_nondet_default, gl.message.raw, u64 ids).

- It does NOT load on a Studio that serves the GenVM v0.2.16 runner (genvm-lint reports E101: runner kz/ybg95x... not found).
- It was not part of the independent audit; the audit findings apply to it by inheritance but were not re-verified here.
- Its 128 direct tests passed with genlayer-test 0.30.0rc2, GENVM_VERSION=v0.6.0-rc15 and cloudpickle installed.
  tests/direct/conftest.py contains a TEST-ONLY patch for a genlayer-test 0.30.0rc2 mock_llm issue; the contract is not touched.
- Linter note for this generation: E010 and E014 are reported but validate.ok is true (false positives).
