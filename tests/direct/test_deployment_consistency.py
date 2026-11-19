"""Source and deployment artifacts must match, and a stale or tampered file must be detected.
Every scenario works on a TEMPORARY COPY of the repository; nothing is broadcast (the GenLayer CLI is replaced by
a recording shim, so the exact commands are asserted without any network access)."""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location("verify_deployment", os.path.join(ROOT, "deploy", "verify_deployment.py"))
vd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vd)

needs_linter = pytest.mark.skipif(shutil.which("genvm-lint") is None, reason="genvm-lint not on PATH")


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "repo"
    for item in ("contracts", "deploy", "abi.json"):
        src = os.path.join(ROOT, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst / item, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.mkdir(exist_ok=True)
            shutil.copy(src, dst / item)
    return dst


def status(results, check):
    return [s for (c, s, _d) in results if c == check][0]


def failed(results):
    return sorted(c for (c, s, _d) in results if s == "FAIL")


@needs_linter
def test_the_committed_repository_is_consistent():
    results = vd.verify(ROOT)
    assert failed(results) == [] and all(s == "PASS" for (_c, s, _d) in results), results


@needs_linter
def test_modified_contract_is_detected(repo):
    p = repo / "contracts" / "truth_anchor.py"
    p.write_text(p.read_text() + "\n# stale edit\n")
    assert "contract_sha256_matches_manifest" in failed(vd.verify(str(repo)))


@needs_linter
def test_contract_change_that_alters_the_schema_is_detected_against_the_committed_abi(repo):
    p = repo / "contracts" / "truth_anchor.py"
    p.write_text(p.read_text().replace("    def __init__(self):\n", "    def __init__(self, owner: str = \"\"):\n"))
    f = failed(vd.verify(str(repo)))
    assert "constructor_params_match_manifest" in f and "abi_regenerated_from_source_equals_committed" in f
    assert "contract_sha256_matches_manifest" in f


@needs_linter
def test_tampered_abi_is_detected(repo):
    abi = json.loads((repo / "abi.json").read_text())
    abi["methods"]["register_event"]["params"].pop()
    (repo / "abi.json").write_text(json.dumps(abi))
    f = failed(vd.verify(str(repo)))
    assert "abi_sha256_matches_manifest" in f and "abi_regenerated_from_source_equals_committed" in f


@needs_linter
def test_a_second_deployable_copy_is_detected(repo):
    (repo / "legacy").mkdir()
    shutil.copy(repo / "contracts" / "truth_anchor.py", repo / "legacy" / "truth_anchor_old.py")
    assert "single_deployable_source" in failed(vd.verify(str(repo)))


@needs_linter
def test_constructor_args_that_do_not_match_the_signature_are_detected(repo):
    (repo / "deploy" / "constructor_args.json").write_text('["0xabc"]')
    assert "constructor_args_match_signature" in failed(vd.verify(str(repo)))


@needs_linter
def test_deploy_script_pointing_at_another_file_is_detected(repo):
    p = repo / "deploy" / "deploy.sh"
    p.write_text(p.read_text().replace("contracts/truth_anchor.py", "contracts/old_truth_anchor.py"))
    assert "deploy_script_uses_only_the_authoritative_source" in failed(vd.verify(str(repo)))


@needs_linter
def test_header_or_runner_drift_is_detected(repo):
    p = repo / "contracts" / "truth_anchor.py"
    p.write_text(p.read_text().replace("py-genlayer:1jb45aa8", "py-genlayer:kzybg95x", 1))
    f = failed(vd.verify(str(repo)))
    assert "header_matches_manifest" in f and "runner_matches_manifest" in f


@needs_linter
def test_unknown_network_is_detected(repo):
    m = json.loads((repo / "deploy" / "deployment.json").read_text())
    m["network"]["default"] = "mainnet-for-real"
    (repo / "deploy" / "deployment.json").write_text(json.dumps(m))
    assert "network_configuration_is_known" in failed(vd.verify(str(repo)))


def test_manifest_records_that_no_live_deployment_was_performed():
    m = json.load(open(os.path.join(ROOT, "deploy", "deployment.json")))
    assert m["live_deployment_performed"] is False and m["constructor"]["params"] == []
    assert json.load(open(os.path.join(ROOT, "deploy", "constructor_args.json"))) == []
    assert m["network"]["default"] == "localnet"


# --------------------------------- the deploy script, with a recording CLI shim ---------------------------------
def run_script(repo, tmp_path, env_extra):
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    log = tmp_path / "cli_calls.log"
    shim = shim_dir / "genlayer"
    shim.write_text("#!/usr/bin/env bash\necho \"$@\" >> \"%s\"\n" % log)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=str(shim_dir) + os.pathsep + os.environ["PATH"], **env_extra)
    env.pop("CONFIRM_DEPLOY", None) if "CONFIRM_DEPLOY" not in env_extra else None
    p = subprocess.run(["bash", str(repo / "deploy" / "deploy.sh")], capture_output=True, text=True, env=env, cwd=str(repo))
    calls = log.read_text().strip().split("\n") if log.exists() and log.read_text().strip() else []
    return p, calls


@needs_linter
def test_deploy_script_never_calls_the_cli_without_explicit_confirmation(repo, tmp_path):
    p, calls = run_script(repo, tmp_path, {})
    assert p.returncode == 1 and "CONFIRM_DEPLOY=yes" in p.stderr and calls == []


@needs_linter
def test_deploy_script_issues_exactly_the_expected_commands_when_confirmed(repo, tmp_path):
    """The CLI is a recording shim: this proves the command line, not a deployment."""
    p, calls = run_script(repo, tmp_path, {"CONFIRM_DEPLOY": "yes"})
    assert p.returncode == 0, p.stdout + p.stderr
    assert calls == ["network set localnet", "deploy --contract contracts/truth_anchor.py"]     # no --args: constructor is empty


@needs_linter
def test_deploy_script_refuses_when_the_contract_was_changed_after_the_manifest(repo, tmp_path):
    c = repo / "contracts" / "truth_anchor.py"
    c.write_text(c.read_text() + "\n# changed\n")
    p, calls = run_script(repo, tmp_path, {"CONFIRM_DEPLOY": "yes"})
    assert p.returncode != 0 and calls == []


@needs_linter
def test_network_can_only_be_changed_explicitly(repo, tmp_path):
    p, calls = run_script(repo, tmp_path, {"CONFIRM_DEPLOY": "yes", "NETWORK": "studionet"})
    assert p.returncode == 0 and calls[0] == "network set studionet"
