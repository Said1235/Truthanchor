import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

"""Direct-mode test setup for TruthAnchor, SDK generation A (runner py-genlayer:1jb45aa8...).

Use genlayer-test==0.29.2 here (0.30.0rc2 cannot load generation-A contracts; see playbook 5.3).
genlayer-test 0.29.2 picks the first GenVM bundle cached in ~/.cache/gltest-direct and, if none is
cached, tries to download 'latest' (a 404 today). We seed the cache with v0.2.16, the bundle that
contains runner 1jb45aa8..., from the genvm-lint cache (`genvm-lint download -v v0.2.16`).
No mock patch is needed: in generation A the json mock for exec_prompt must arrive pre-parsed.
"""
os.environ.setdefault("GENVM_VERSION", "v0.2.16")   # used by genvm-lint (subprocess test)


def _seed_bundle():
    cache = os.path.expanduser("~/.cache/gltest-direct")
    target = os.path.join(cache, "genvm-universal-v0.2.16.tar.xz")
    if os.path.exists(target):
        return
    source = os.path.expanduser("~/.cache/genvm-linter/genvm-universal-v0.2.16.tar.xz")
    if os.path.exists(source):
        os.makedirs(cache, exist_ok=True)
        shutil.copy(source, target)


_seed_bundle()

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
