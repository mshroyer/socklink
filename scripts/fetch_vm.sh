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

# Reports an error, as an annotation if running in GitHub Actions.
error() {
	if [ "$GITHUB_ACTIONS" = true ]; then
		echo "::error::$1" >&2
	else
		echo "$1" >&2
	fi
}

HELP="See \"Forking and GitHub Actions\" in CONTRIBUTING.md for how to set up a bucket of test VM images."

if [ -f "$PROJECT/vms/${vm_name}.qcow2" ]; then
	echo "$PROJECT/vms/${vm_name}.qcow2 already exists!" >&2
	exit 1
fi

if [ -f "$CACHE/${vm_name}.qcow2.zst" ]; then
	echo "Cached download for ${vm_name} already present, skipping download"
else
	required_vars="\
SOCKLINK_TEST_VMS_S3_ENDPOINT
SOCKLINK_TEST_VMS_S3_BUCKET
SOCKLINK_TEST_VMS_ACCESS_KEY_ID
SOCKLINK_TEST_VMS_SECRET_ACCESS_KEY
"
	missing=
	for var in $required_vars; do
		eval "value=\${$var}"
		if [ -z "$value" ]; then
			missing="$missing $var"
		fi
	done
	if [ -n "$missing" ]; then
		error "Can't fetch VM ${vm_name}, missing:${missing}. $HELP"
		exit 1
	fi

	env AWS_ACCESS_KEY_ID="${SOCKLINK_TEST_VMS_ACCESS_KEY_ID}" \
	    AWS_SECRET_ACCESS_KEY="${SOCKLINK_TEST_VMS_SECRET_ACCESS_KEY}" \
	    AWS_DEFAULT_REGION=auto \
	    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
	    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
	    aws s3 cp "--endpoint-url=$SOCKLINK_TEST_VMS_S3_ENDPOINT" \
	    "s3://${SOCKLINK_TEST_VMS_S3_BUCKET}/${vm_name}.qcow2.zst" "$CACHE" || {
		error "Failed to fetch ${vm_name}.qcow2.zst from bucket ${SOCKLINK_TEST_VMS_S3_BUCKET}. $HELP"
		exit 1
	}
fi

if [ ! -d "$PROJECT/vms" ]; then
	mkdir "$PROJECT/vms"
fi
zstd --output-dir-flat "$PROJECT/vms" -d "$CACHE/${vm_name}.qcow2.zst"
