#!/bin/sh

# Query available tmux features
#
# Intended to be used in .tmux.conf via if-shell so we don't attempt to set
# unavailable features (and cause annoying error messages) on systems with old
# versions of tmux.
#
# Note that on OpenBSD, tmux is in the base system and its version gets
# reported as openbsd-7.6, with the OS version instead of a tmux version
# number.  So version number-based checks have to consider two possible ranges
# of versions.

set -e

show_usage() {
cat <<'EOF'
tmux_feature.sh - Test for available tmux features

Exits with a nonzero code if the requested feature is unavailable.

Usage:
    tmux_feature.sh client-active-hook
EOF
}

TV="$(tmux -V)"
TV_PREFIX="$(echo "$TV" | sed -E 's/^tmux ((.*)-)?([0-9]+\.[0-9]+)(.*)/\2/')"
TV_NUMBER="$(echo "$TV" | sed -E 's/^tmux ((.*)-)?([0-9]+\.[0-9]+)(.*)/\3/')"

check_number_at_least() {
	if [ "$(echo "$TV_NUMBER >= $1" | bc)" != "1" ]; then
		exit 1
	fi
}

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "client-active-hook" ]; then
	if [ -z "$TV_PREFIX" ]; then
		check_number_at_least 3.3
	elif [ "$TV_PREFIX" = "openbsd" ]; then
		check_number_at_least 7.1
	else
		exit 1
	fi
else
	show_usage
	exit 1
fi
