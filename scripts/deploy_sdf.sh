#!/bin/sh

set -e

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

scp "$PROJECT/socklink.sh" rie.sdf.org:
scp "$PROJECT/socklink.sh" ma.sdf.org:
