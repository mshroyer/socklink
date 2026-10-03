#!/bin/sh

# Run tsock.sh's Python-based test suite
#
# Finds an appropriate version of Python, sets up a virtual environment in
# .venv, installs test dependencies, and runs the tests.  This script is meant
# to work on all platforms where socklink.sh runs.

set -e

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPTS/lib"

PYTHON_MIN=3.11
PYTHON_BINS="python3.15 python3.14 python3.13 python3.12 python3.11 python3 python"

RETRIES_FLAG=
if [ "$(uname)" = "Darwin" ]; then
	# On macOS I've been unable to find a non-flaky means of capturing
	# stdout from shell commands run within tmux in pexpect sessions, so
	# let's specifically enable retries there to minimize workflow
	# failures.
	RETRIES_FLAG='--retries=2'

	# Fix max path issues.
	PYTEST_DEBUG_TEMPROOT=/tmp
	export PYTEST_DEBUG_TEMPROOT
fi

python_version_at_least() {
	result=$("$1" -c "import sys; print(float(f'{sys.version_info[0]}.{sys.version_info[1]}') >= $2)")
	if [ "$result" != "True" ]; then
		false
	fi
}

# Searches Python binary candidate names for the first one matching our
# minimum version requirement.
get_python_bin() {
	for bin in $PYTHON_BINS; do
		if which "$bin" >/dev/null 2>&1 \
				&& python_version_at_least "$bin" "$PYTHON_MIN"; then
			ver=$("$bin" --version)
			printf "\n======================================================================\n" >&2
			printf "                        SOCKLINK TEST SUITE\n\n" >&2
			uname -a >&2
			if [ -f /etc/os-release ]; then
				grep PRETTY_NAME /etc/os-release >&2
			fi
			tmux -V >&2
			echo "Using bin $bin, version $ver" >&2
			printf "======================================================================\n\n" >&2
			echo "$bin"
			return
		fi
	done
	echo "No supported Python version found, aborting" >&2
	exit 1
}

setup_venv() {
	if [ ! -d "${PROJECT}/.venv" ]; then
		echo "Preparing venv"
		py="$(get_python_bin)"
		"$py" -m venv "${PROJECT}/.venv"
	fi
}

run_tests_in_container() {
	distro="$1"
	shift

	if [ ! -d "$PROJECT/containers/$distro" ]; then
		echo "Unknown container distro: $distro" >&2
		exit 1
	fi

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
		  "$(cat "$IMAGE_ID")" "/socklink/scripts/test.sh"
}

run_tests_in_vm() {
	vm="$1"

	setup_venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/python "$PROJECT/scripts/vm_test.py" "$vm"
}

run_tests_in_all_containers_and_vms() {
	for c in "$PROJECT/containers"/*; do
		if [ -d "$c" ]; then
			c="$(basename "$c")"
			run_tests_in_container "$c"
		fi
	done
	for m in "$PROJECT/vms"/*.qcow2; do
		if [ -f "$m" ]; then
			m="$(basename "$m")"
			m="${m%.qcow2}"
			run_tests_in_vm "$m"
		fi
	done
}

# shellcheck disable=SC2120
run_tests() {
	cd "$PROJECT" || exit 1

	# Delete any per-container "files" directories copied over by
	# run_in_container in order to prevent pytest from getting confused
	# about non-toplevel conftest.py files.
	for distro in ./containers/*; do
		rm -rf "$distro/files"
	done

	setup_venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/python -m pytest $RETRIES_FLAG -v "$PYTEST_ARG"
}

all_flag=
container_flag=
vm_flag=
while getopts ac:m:h flag
do
	case "$flag" in
		a)
			all_flag=1
			;;

		c)
			container_flag="$OPTARG"
			;;

		m)
			vm_flag="$OPTARG"
			;;

		*)
		        echo "Unknown flag: $flag" >&2
			exit 1
			;;
	esac
done
shift $((OPTIND - 1))

if [ -n "$1" ]; then
	PYTEST_ARG="$1"
fi

if [ -n "$all_flag" ]; then
	make_ci_iso
	run_tests_in_all_containers_and_vms
elif [ -n "$container_flag" ]; then
	run_tests_in_container "$container_flag"
elif [ -n "$vm_flag" ]; then
	make_ci_iso
	run_tests_in_vm "$vm_flag"
else
	run_tests
fi
