#!/bin/sh

# Run tsock.sh's Python-based test suite
#
# Finds an appropriate version of Python, sets up a virtual environment in
# .venv, installs test dependencies, and runs the tests.  This script is meant
# to work on all platforms where socklink.sh runs.

set -e

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPTS/lib"

show_usage() {
	cat <<'EOF'
test.sh - Run tests for socklink.sh

Usage:
    test.sh [test_name]
    test.sh -c container_name [test_name]
    test.sh -m vm_name [test_name]
    test.sh -l
    test.sh -h
EOF
}

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
	.venv/bin/python "$PROJECT/scripts/vm_test.py" "$vm" "$PYTEST_ARG"
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

	printf "\n======================================================================\n" >&2
	printf "                        SOCKLINK TEST SUITE\n\n" >&2
	uname -a >&2
	if [ -f /etc/os-release ]; then
		grep PRETTY_NAME /etc/os-release >&2
	fi
	.venv/bin/python --version >&2
	tmux -V >&2
	printf "======================================================================\n\n" >&2

	.venv/bin/python -m pytest $RETRIES_FLAG -v "$PYTEST_ARG"
}

list_containers_and_vms() {
	echo "Available containers (test.sh -c):"
	for c in "$PROJECT/containers"/*; do
		if [ -d "$c" ]; then
			c="$(basename "$c")"
			echo "- $c"
		fi
	done
	echo
	echo "Available VMs (test.sh -m):"
	for m in "$PROJECT/vms"/*.qcow2; do
		if [ -f "$m" ]; then
			m="$(basename "$m")"
			m="${m%.qcow2}"
			echo "- $m"
		fi
	done
}

all_flag=
container_flag=
vm_flag=
list_flag=
help_flag=
while getopts ac:m:lh flag
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

		l)
			list_flag=1
			;;

		h)
			help_flag=1
			;;

		*)
		        echo "Unknown flag: $flag" >&2
			show_usage
			exit 1
			;;
	esac
done
shift $((OPTIND - 1))

if [ -n "$1" ]; then
	PYTEST_ARG="$1"
fi

if [ -n "$help_flag" ]; then
	show_usage
	exit
elif [ -n "$list_flag" ]; then
	list_containers_and_vms
	exit
elif [ -n "$all_flag" ]; then
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
