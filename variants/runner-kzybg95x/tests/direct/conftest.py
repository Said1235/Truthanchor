import sys, os
sys.path.insert(0, os.path.dirname(__file__))
"""Direct-mode test setup for TruthAnchor (SDK generation B).

1. Pin the GenVM bundle: with GitHub's API rate-limited, genlayer-test falls back to
   a bundle that lacks runner kzybg95x...; v0.6.0-rc15 contains it.
2. TEST-ONLY mitigation for genlayer-test 0.30.0rc2: wasi_mock._handle_llm_request
   auto-parses JSON strings into dicts (right for generation A, wrong for B).
   Return the mock verbatim. The contract is never touched.
"""
import os

os.environ.setdefault("GENVM_VERSION", "v0.6.0-rc15")

import gltest.direct.wasi_mock as _wm  # noqa: E402

_orig = _wm._handle_llm_request


def _handle_llm_request_raw(vm, data):
    response = vm._match_llm_mock(data.get("prompt", ""))
    if response is not None:
        return {"ok": response}
    return _orig(vm, data)


_wm._handle_llm_request = _handle_llm_request_raw


import pytest  # noqa: E402

from helpers import NOW_ISO  # noqa: E402


@pytest.fixture
def ta(direct_vm, direct_deploy, direct_alice):
    direct_vm.strict_mocks = True
    direct_vm.check_pickling = True
    direct_vm.warp(NOW_ISO)
    c = direct_deploy("contracts/truth_anchor.py")
    direct_vm.sender = direct_alice
    return c


@pytest.fixture
def mod(ta):
    from helpers import load_module
    return load_module()
