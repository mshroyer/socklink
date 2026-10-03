#!/bin/sh

set -e

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPTS/lib"

CACHE="$PROJECT/cache"

if [ ! -d "$CACHE" ]; then
	mkdir "$CACHE"
fi

vm_name="$1"
test -n "$vm_name" || exit 1

if [ -f "$PROJECT/vms/${vm_name}.qcow2" ]; then
	echo "$PROJECT/vms/${vm_name}.qcow2 already exists!" >&2
	exit 1
fi

if [ -f "$CACHE/${vm_name}.qcow2.zst" ]; then
	echo "Cached download for ${vm_name} already present, skipping download"
else
	env AWS_ACCESS_KEY_ID="${SOCKLINK_TEST_VMS_ACCESS_KEY_ID}" \
	    AWS_SECRET_ACCESS_KEY="${SOCKLINK_TEST_VMS_SECRET_ACCESS_KEY}" \
	    AWS_DEFAULT_REGION=auto \
	    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
	    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
	    aws s3 cp "--endpoint-url=$TEST_VMS_S3_ENDPOINT" \
	    "s3://${TEST_VMS_S3_BUCKET}/${vm_name}.qcow2.zst" "$CACHE"
fi

zstd --output-dir-flat "$PROJECT/vms" -d "$CACHE/${vm_name}.qcow2.zst"
