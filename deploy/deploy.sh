#!/usr/bin/env bash
# Deploys the authoritative TruthAnchor contract with the GenLayer CLI (verified against genlayer 0.39.2).
#
#   CONFIRM_DEPLOY=yes [NETWORK=localnet|studionet|testnet-asimov|testnet-bradbury] deploy/deploy.sh
#
# Safety:
#   * It first runs deploy/verify_deployment.py and aborts if the source, header, constructor, ABI or manifest disagree.
#   * It refuses to run without CONFIRM_DEPLOY=yes, so it can never broadcast by accident.
#   * The constructor takes no arguments; the arguments come only from deploy/constructor_args.json.
#   * This script was NOT executed during the remediation: no live deployment was performed.
set -euo pipefail
cd "$(dirname "$0")/.."

python deploy/verify_deployment.py

if [ "${CONFIRM_DEPLOY:-}" != "yes" ]; then
  echo "Refusing to deploy: set CONFIRM_DEPLOY=yes to broadcast a deployment transaction." >&2
  exit 1
fi

NETWORK="${NETWORK:-$(python -c "import json; print(json.load(open('deploy/deployment.json'))['network']['default'])")}"
genlayer network set "$NETWORK"

ARGS="$(python -c "import json; print(' '.join(json.dumps(a) for a in json.load(open('deploy/constructor_args.json'))))")"
if [ -n "$ARGS" ]; then
  # shellcheck disable=SC2086
  genlayer deploy --contract contracts/truth_anchor.py --args $ARGS
else
  genlayer deploy --contract contracts/truth_anchor.py
fi
