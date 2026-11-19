"""Mutation check: weaken one security defence at a time in a temporary copy of the contract and verify that
the direct suite FAILS. A surviving mutant means the suite does not protect that defence.

Usage (from the repository root, with GENVM_VERSION=v0.2.16 and genlayer-test 0.29.2 installed):
    python tools/mutation_check.py            # all mutants
    python tools/mutation_check.py M07 M09    # selected mutants
The contract file is restored byte-for-byte after every mutant, even on error."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "contracts", "truth_anchor.py")

MUTANTS = [
    ("M01", "markup scanner rescans after a tag (quadratic/incorrect)", "work += gt - j\n            i = gt + 1", "work += gt - j\n            i = j + 1"),
    ("M02", "no minimum excerpt length", "MIN_EXCERPT_CHARS = 40 ", "MIN_EXCERPT_CHARS = 1 "),
    ("M03", "no minimum excerpt word count", "MIN_EXCERPT_WORDS = 6\n", "MIN_EXCERPT_WORDS = 1\n"),
    ("M04", "no lexical anchoring of the excerpt to the proposition", "need = min(2, len(anchors))", "need = 0"),
    ("M05", "entailment verdict ignored on the leader side", 'r2 = rel["own-%d" % i]', "r2 = c"),
    ("M06", "registered publisher/domain groups not merged", "if pubs[i] == pubs[j]:\n                union(i, j)", "if False:\n                union(i, j)"),
    ("M07", "identical/near-identical page content not merged", "if texts[i] == texts[j] or _near_duplicate(sh[i], sh[j]):", "if False:"),
    ("M08", "identical excerpt through different pages not merged", 'if exs[i] != "" and exs[i] == exs[j]:', "if False:"),
    ("M09", "no eligibility check on resolution", "if now_ts < earliest:", "if False:"),
    ("M10", "temporary failures finalise the event", "if temporary and not final_attempt:\n        return LC_OPEN, RSN_TEMPORARY, s, c", "if False:\n        return LC_OPEN, RSN_TEMPORARY, s, c"),
    ("M11", "validator accepts without independent comparison", "return _validator_agrees(data, mine, urls, final_attempt)", "return True"),
    ("M12", "closure condition removed", "final_attempt = attempts >= RETRY_CLOSURE_ATTEMPTS and now_ts >= earliest + RETRY_CLOSURE_WINDOW_SECONDS", "final_attempt = False"),
    ("M13", "caller proposition appended outside the JSON data", '"TASK: SOURCE ANALYSIS\\n" + _POLICY + _ANALYSIS_SPEC', '"TASK: SOURCE ANALYSIS\\n" + _POLICY + _ANALYSIS_SPEC + "\\nPROPOSITION: " + proposition'),
    ("M14", "oversized raw body is processed", 'if len(body) > MAX_RAW_BYTES:\n        return RS_OVERSIZED, ""', "if False:\n        return RS_OVERSIZED, \"\""),
    ("M15", "validator ignores the entailment of the leader's excerpt", 'if mine["lead_rel"].get(i, 0) != a["classification"]:\n                return False', 'if False:\n                return False'),
    ("M16", "validator fails open on its own errors", "except Exception:\n                return False", "except Exception:\n                return True"),
    ("M17", "validator accepts leader errors", "return False  # leader UserError / VMError / unknown: never accept, force rotation", "return True"),
    ("M18", "a finalised event can be resolved again", '_err("EXPECTED", "event is not open")', "pass"),
    ("M19", "oversized extracted text is accepted", 'if len(text) > MAX_TEXT_CHARS:\n        return RS_OVERSIZED, ""', "if False:\n        return RS_OVERSIZED, \"\""),
    ("M20", "404 and incomplete responses are not retryable", "TEMPORARY_RS = (RS_EMPTY, RS_FETCH_ERROR, RS_HTTP_TEMPORARY, RS_NOT_FOUND)", "TEMPORARY_RS = (RS_FETCH_ERROR, RS_HTTP_TEMPORARY)"),
    ("M21", "web exceptions are not retryable", "    except Exception:\n        return RS_FETCH_ERROR, \"\"", "    except Exception:\n        return RS_HTTP_PERMANENT, \"\""),
]


def run_suite():
    env = dict(os.environ, GENVM_VERSION=os.environ.get("GENVM_VERSION", "v0.2.16"),
               PYTHONPATH=os.path.join(ROOT, "tests", "direct"))
    # The deployment-consistency tests compare the contract hash with the manifest, so ANY mutation would fail them
    # for a trivial reason. They are excluded: a mutant must be killed by a behavioural test.
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/direct", "-x", "-q", "-p", "no:cacheprovider",
                        "--ignore=tests/direct/test_deployment_consistency.py"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    last = [l for l in (p.stdout + p.stderr).replace("\r", "\n").split("\n") if "passed" in l or "failed" in l or "error" in l.lower()]
    return p.returncode, (last[-1].strip() if last else "")


def main(argv):
    wanted = set(argv)
    original = open(CONTRACT, "rb").read()
    backup = CONTRACT + ".orig"
    shutil.copyfile(CONTRACT, backup)
    survivors = []
    try:
        for mid, desc, old, new in MUTANTS:
            if wanted and mid not in wanted:
                continue
            text = original.decode("utf-8")
            if text.count(old) < 1:
                print("%s  SKIPPED (pattern not found)  %s" % (mid, desc))
                survivors.append(mid)
                continue
            open(CONTRACT, "w").write(text.replace(old, new))
            code, summary = run_suite()
            killed = code != 0
            print("%s  %s  | %s | %s" % (mid, "KILLED  " if killed else "SURVIVED", desc, summary))
            if not killed:
                survivors.append(mid)
    finally:
        open(CONTRACT, "wb").write(original)
        os.remove(backup)
    print("restored contract: %s" % ("identical" if open(CONTRACT, "rb").read() == original else "DIFFERENT"))
    print("survivors: %s" % (survivors or "none"))
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
