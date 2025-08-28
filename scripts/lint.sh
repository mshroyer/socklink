#!/bin/sh

# Lint all sources.  Needs emacs, shellcheck, and ruff installed.

set -e

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

cd "$PROJECT"

printf "## Linting shell scripts:\n\n"
scripts/format.sh check
scripts/format.sh shellcheck

printf "\n## Linting Python:\n\n"
ruff check
ruff format --diff
