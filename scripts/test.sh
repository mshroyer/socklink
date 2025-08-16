#!/bin/sh

# Run tsock.sh's Python-based test suite
#
# Finds an appropriate version of Python, sets up a virtualenv in .venv,
# installs dependencies, and runs the tests.

set -e

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

get_system_python() {
	supported_pythons="python3.13 python3.12 python3.11"
	for python_version in $supported_pythons; do
		if which $python_version >/dev/null 2>&1; then
			echo $python_version
			return
		fi
	done
	echo "No supported Python version found, aborting" >&2
	exit 1
}

setup_venv() {
	if [ ! -d "${PROJECT}/.venv" ]; then
		echo "Preparing venv"
		py="$(get_system_python)"
		"$py" -m venv "${PROJECT}/.venv"
	fi
	. "${PROJECT}/.venv/bin/activate"
	pip install pip-tools
}

setup_venv
pip-sync
pytest -v $@
