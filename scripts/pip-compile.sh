#!/bin/sh

set -e

pip-compile pyproject.toml "$@"
pip-compile --extra dev -c requirements.txt pyproject.toml "$@" -o dev-requirements.txt
