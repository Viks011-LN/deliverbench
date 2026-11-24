#!/usr/bin/env bash
# F03: build the base image from images/base alone and check what a job's main room starts with.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${CHECK_TAG:-deliverbench-base:0.1.0}"   # CHECK_TAG points the checks at another image (to test the test)

if [ -z "${CHECK_TAG:-}" ]; then
  docker build --quiet --tag "$TAG" images/base >/dev/null
  echo "built $TAG"
fi

fail() { echo "FAIL: $1"; exit 1; }
inside() { docker run --rm --network none "$TAG" bash -c "$1"; }

[ "$(inside 'id -u')" = "1000" ] || fail "does not run as uid 1000"
[ "$(inside 'whoami')" = "agent" ] || fail "user is not agent"
[ "$(inside 'pwd')" = "/app" ] || fail "working directory is not /app"
inside 'python -V' | grep -q "^Python 3\.12\." || fail "python is not 3.12"
inside 'python -c "import numpy, pandas, scipy, statsmodels, flask, requests, pytest"' || fail "a library does not import"
inside 'for t in bash curl git jq ps less; do command -v $t >/dev/null || exit 1; done' || fail "a command-line tool is missing"
inside 'test ! -e /tests && test ! -e /solution && test ! -e /checks' || fail "a tests or solution folder exists in the image"
inside 'touch /app/probe && rm /app/probe' || fail "agent cannot write to /app"
if inside 'touch /usr/probe' 2>/dev/null; then fail "agent can write outside /app and /tmp"; fi
if docker run --rm --network none "$TAG" python -c "import urllib.request as u; u.urlopen('http://example.com', timeout=3)" 2>/dev/null; then
  fail "network reachable with --network none"
fi

echo "base image OK: uid 1000 agent in /app, python 3.12, libraries import, tools present, no tests or solutions, no network"
