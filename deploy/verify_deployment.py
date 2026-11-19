#!/usr/bin/env python3
"""Consistency check between the authoritative contract and every deployment artifact.

It never touches a network and never broadcasts a transaction. It fails (exit 1) when the contract source,
its header, the constructor, the committed ABI, the manifest, the constructor arguments or the deploy script
disagree, or when a second deployable contract source exists in the repository.

    python deploy/verify_deployment.py            # verify
    python deploy/verify_deployment.py --write    # refresh manifest hashes and abi.json from the contract

Statuses: PASS, FAIL, BLOCKED (a required tool, such as genvm-lint, is not available).
"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_NETWORKS = ("localnet", "studionet", "testnet-asimov", "testnet-bradbury")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "artifacts", ".pytest_cache"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def find_contract_sources(root):
    """Every file that could be deployed as an Intelligent Contract (gl.Contract subclass or runner header)."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                text = open(path, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            if os.path.relpath(path, root).split(os.sep)[0] == "tests":
                continue
            head = "\n".join(text.split("\n")[:3])
            is_contract = bool(re.search(r'^# \{ "Depends": "py-genlayer:', head, re.M))
            try:
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.ClassDef) and any(
                        isinstance(b, ast.Attribute) and b.attr == "Contract" for b in node.bases
                    ):
                        is_contract = True
            except SyntaxError:
                pass
            if is_contract:
                found.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return sorted(found)


def constructor_params(contract_path):
    tree = ast.parse(open(contract_path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
            isinstance(b, ast.Attribute) and b.attr == "Contract" for b in node.bases
        ):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    a = item.args
                    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
                    if a.vararg:
                        names.append("*" + a.vararg.arg)
                    if a.kwarg:
                        names.append("**" + a.kwarg.arg)
                    return [n for n in names if n != "self"]
            return None
    return None


def regenerate_abi(root, contract_rel, bundle):
    exe = shutil.which("genvm-lint")
    if exe is None:
        return None, "genvm-lint not found on PATH"
    out = os.path.join(tempfile.mkdtemp(), "abi.json")
    env = dict(os.environ, GENVM_VERSION=bundle)
    p = subprocess.run([exe, "schema", os.path.join(root, contract_rel), "--output", out],
                       capture_output=True, text=True, env=env)
    if p.returncode != 0 or not os.path.exists(out):
        return None, (p.stdout + p.stderr)[-400:]
    return out, ""


def verify(root=DEFAULT_ROOT):
    results = []

    def add(check, status, detail=""):
        results.append((check, status, detail))

    mpath = os.path.join(root, "deploy", "deployment.json")
    try:
        m = json.load(open(mpath))
        add("manifest_parses", "PASS", mpath)
    except (OSError, ValueError) as e:
        add("manifest_parses", "FAIL", str(e))
        return results
    contract_rel = m["contract_path"]
    contract = os.path.join(root, contract_rel)
    if not os.path.exists(contract):
        add("authoritative_contract_exists", "FAIL", contract_rel)
        return results
    add("authoritative_contract_exists", "PASS", contract_rel)

    sources = find_contract_sources(root)
    add("single_deployable_source", "PASS" if sources == [contract_rel] else "FAIL",
        "found: %s expected: [%s]" % (sources, contract_rel))

    actual = sha256_file(contract)
    add("contract_sha256_matches_manifest", "PASS" if actual == m["contract_sha256"] else "FAIL",
        "actual %s manifest %s" % (actual, m["contract_sha256"]))

    lines = open(contract, encoding="utf-8").read().split("\n")
    add("header_matches_manifest", "PASS" if lines[:2] == m["header"] else "FAIL", "%r vs %r" % (lines[:2], m["header"]))
    runner = re.search(r'"Depends":\s*"([^"]+)"', lines[1] if len(lines) > 1 else "")
    add("runner_matches_manifest", "PASS" if runner and runner.group(1) == m["runner"] else "FAIL",
        "%s vs %s" % (runner.group(1) if runner else None, m["runner"]))

    params = constructor_params(contract)
    add("constructor_params_match_manifest", "PASS" if params == m["constructor"]["params"] else "FAIL",
        "contract %s manifest %s" % (params, m["constructor"]["params"]))
    try:
        args = json.load(open(os.path.join(root, m["constructor"]["args_file"])))
    except (OSError, ValueError) as e:
        args = None
        add("constructor_args_parse", "FAIL", str(e))
    if args is not None:
        ok = isinstance(args, list) and len(args) == len(m["constructor"]["params"])
        add("constructor_args_match_signature", "PASS" if ok else "FAIL",
            "args %s for params %s" % (args, m["constructor"]["params"]))

    abi_path = os.path.join(root, m["abi"]["path"])
    if not os.path.exists(abi_path):
        add("abi_exists", "FAIL", m["abi"]["path"])
    else:
        add("abi_sha256_matches_manifest", "PASS" if sha256_file(abi_path) == m["abi"]["sha256"] else "FAIL",
            "actual %s manifest %s" % (sha256_file(abi_path), m["abi"]["sha256"]))
        committed = json.load(open(abi_path))
        add("abi_constructor_has_no_parameters",
            "PASS" if committed.get("ctor") == {"params": [], "kwparams": {}} and not m["constructor"]["params"] else "FAIL",
            str(committed.get("ctor")))
        add("abi_methods_match_manifest", "PASS" if sorted(committed.get("methods", {})) == sorted(m["methods"]) else "FAIL",
            "%s vs %s" % (sorted(committed.get("methods", {})), sorted(m["methods"])))
        fresh, why = regenerate_abi(root, contract_rel, m["genvm_bundle"])
        if fresh is None:
            add("abi_regenerated_from_source_equals_committed", "BLOCKED", why)
        else:
            same = json.load(open(fresh)) == committed
            add("abi_regenerated_from_source_equals_committed", "PASS" if same else "FAIL", "genvm-lint schema")

    script_path = os.path.join(root, "deploy", "deploy.sh")
    try:
        script = open(script_path).read()
    except OSError as e:
        add("deploy_script_exists", "FAIL", str(e))
        script = None
    if script is not None:
        paths = set(re.findall(r"--contract\s+\"?([^\s\"]+)\"?", script))
        add("deploy_script_uses_only_the_authoritative_source", "PASS" if paths == {contract_rel} else "FAIL",
            "contract paths in script: %s" % sorted(paths))
        add("deploy_script_runs_consistency_check_first", "PASS" if "deploy/verify_deployment.py" in script else "FAIL")
        add("deploy_script_requires_explicit_confirmation", "PASS" if "CONFIRM_DEPLOY" in script else "FAIL")
        add("deploy_script_takes_args_from_args_file", "PASS" if m["constructor"]["args_file"] in script else "FAIL")

    nets = m["network"]
    ok = nets["default"] in KNOWN_NETWORKS and set(nets["allowed"]) <= set(KNOWN_NETWORKS) and nets["default"] in nets["allowed"]
    add("network_configuration_is_known", "PASS" if ok else "FAIL", "%s in %s" % (nets["default"], nets["allowed"]))
    add("manifest_states_no_live_deployment", "PASS" if m.get("live_deployment_performed") is False else "FAIL")
    return results


def write(root=DEFAULT_ROOT):
    mpath = os.path.join(root, "deploy", "deployment.json")
    m = json.load(open(mpath))
    contract_rel = m["contract_path"]
    fresh, why = regenerate_abi(root, contract_rel, m["genvm_bundle"])
    if fresh is None:
        raise SystemExit("cannot regenerate the ABI: " + why)
    shutil.copyfile(fresh, os.path.join(root, m["abi"]["path"]))
    abi = json.load(open(fresh))
    m["contract_sha256"] = sha256_file(os.path.join(root, contract_rel))
    m["abi"]["sha256"] = sha256_file(os.path.join(root, m["abi"]["path"]))
    m["methods"] = sorted(abi["methods"])
    json.dump(m, open(mpath, "w"), indent=2)
    open(mpath, "a").write("\n")
    print("manifest and ABI refreshed from", contract_rel)


def main(argv):
    root = DEFAULT_ROOT
    if "--write" in argv:
        write(root)
    results = verify(root)
    width = max(len(r[0]) for r in results)
    for check, status, detail in results:
        print("%-7s %-*s %s" % (status, width, check, detail if status != "PASS" else ""))
    failed = [r for r in results if r[1] == "FAIL"]
    blocked = [r for r in results if r[1] == "BLOCKED"]
    print("\n%d PASS, %d FAIL, %d BLOCKED" % (len(results) - len(failed) - len(blocked), len(failed), len(blocked)))
    return 1 if failed else (2 if blocked else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
