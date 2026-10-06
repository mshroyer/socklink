#!/bin/sh

# Lint all sources.  Needs emacs, shellcheck, and ruff installed.

set -e

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPTS/lib"

cd "$PROJECT"

lint() {
	printf "## Preparinv venv ##\n\n"
	setup_venv
	.venv/bin/pip install -r dev-requirements.txt

	printf "\n## Linting shell scripts:\n\n"
	scripts/format.sh check
	scripts/format.sh shellcheck

	printf "\n## Linting Python:\n\n"
	.venv/bin/ruff check
	.venv/bin/ruff format --diff
}

# Runs the lints in the Ubuntu 26.04 container in order to match the versions
# of emacs and shellcheck used in the GitHub Actions runner.
lint_in_container() {
	distro=ubuntu2604

	copy_ci_requirements "$PROJECT/containers/$distro/files/socklink"

	DOCKER="$(find_docker)"
	FILES_CACHEBUST="$(latest_mtime_recursive "$PROJECT/containers/$distro")"
	IMAGE_ID="$(mktemp)"
	trap "rm -f $IMAGE_ID" EXIT

	"$DOCKER" build --iidfile="$IMAGE_ID" "$PROJECT/containers/$distro" \
		  "--build-arg=files_cachebust=$FILES_CACHEBUST"
	echo "$DOCKER" run -e "PYTEST_ARG=$PYTEST_ARG" --rm \
	     "$(cat "$IMAGE_ID")" "/socklink/scripts/test.sh"
	"$DOCKER" run -e "PYTEST_ARG=$PYTEST_ARG" --rm \
		  "$(cat "$IMAGE_ID")" "/socklink/scripts/lint.sh"
}

container_flag=
while getopts c flag
do
	case "$flag" in
		c)
			container_flag=1
			;;

		*)
		        echo "Unknown flag: $flag" >&2
			show_usage
			exit 1
			;;
	esac
done
shift $((OPTIND - 1))

if [ -n "$container_flag" ]; then
	lint_in_container
else
	lint
fi
