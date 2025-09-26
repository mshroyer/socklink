#!/bin/sh

# Deploys the checked out version of socklink to SDF.  Should be run on the
# regular cluster.

set -e

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

install "$PROJECT/socklink.sh" "$HOME/socklink.sh"
install "$PROJECT/socklink.sh" /sys/sdf/bin/socklink.sh
scp "$PROJECT/socklink.sh" ma.sdf.org:
