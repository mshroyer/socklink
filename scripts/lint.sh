#!/bin/sh

SCRIPTS="$(dirname "$0")"

set -e

printf "## Linting shell scripts:\n\n"
"$SCRIPTS/format.sh" check
"$SCRIPTS/format.sh" shellcheck

printf "\n## Linting Python:\n\n"
ruff check
ruff format --diff
