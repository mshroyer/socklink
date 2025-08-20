#!/bin/sh

# Run tsock.sh's Python-based test suite
#
# Finds an appropriate version of Python, sets up a virtual environment in
# .venv, installs test dependencies, and runs the tests.

set -e

PYTHON_MIN=3.11
PYTHON_BINS="python3.13 python3.12 python3.11 python3 python"

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

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
		if which $bin >/dev/null 2>&1 \
				&& python_version_at_least $bin $PYTHON_MIN; then
			echo $bin
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
	. "${PROJECT}/.venv/bin/activate"
	pip install -r requirements.txt
}

setup_venv
pytest -v $@
