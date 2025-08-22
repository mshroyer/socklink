#!/bin/sh

# Uploads release artifacts once we have a tagged and verified release.

set -e

python3 scripts/release.py upload tsock.sh
