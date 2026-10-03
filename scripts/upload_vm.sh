#!/bin/sh

set -e

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPTS/lib"

vm_name="$1"
test -n "$vm_name" || exit 1

VM="$PROJECT/vms/${vm_name}.qcow2"
if [ ! -f "$VM" ]; then
	echo "$VM does not exist!" >&2
	exit 1
fi

CACHE="$PROJECT/cache"
if [ ! -d "$CACHE" ]; then
	mkdir "$CACHE"
fi

CACHE_FILE="$CACHE/${vm_name}.qcow2.zst"
rm -f "$CACHE_FILE"
echo "Compressing to $CACHE_FILE..."
zstd -19 --output-dir-flat "$CACHE" "$VM"

echo "Uploading to bucket..."
env AWS_ACCESS_KEY_ID="${SOCKLINK_TEST_VMS_ACCESS_KEY_ID}" \
    AWS_SECRET_ACCESS_KEY="${SOCKLINK_TEST_VMS_SECRET_ACCESS_KEY}" \
    AWS_DEFAULT_REGION=auto \
    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    aws s3 cp "--endpoint-url=$TEST_VMS_S3_ENDPOINT" \
    "$CACHE_FILE" "s3://${TEST_VMS_S3_BUCKET}/"
