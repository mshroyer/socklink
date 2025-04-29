#!/bin/sh

# Query available tmux features

set -e

show_usage() {
cat <<'EOF'
tmux_feature.sh - Test for available tmux features

Exits with a nonzero code if the requested feature is unavailable.

Usage:
    tmux_feature.sh client-active-hook
EOF
}

TV_NUMBER="$(tmux -V | sed -E 's/^tmux ((.*)-)?([0-9]\.[0-9])(.*)/\3/')"
TV_PREFIX="$(tmux -V | sed -E 's/^tmux ((.*)-)?([0-9]\.[0-9])(.*)/\2/')"

check_number_at_least() {
	if [ "$(echo "$TV_NUMBER >= $1" | bc)" != "1" ]; then
		exit 1
	fi
}

check_client_active_hook() {
	if [ -z "$TV_PREFIX" ]; then
		check_number_at_least 3.3
	elif [ "$TV_PREFIX" = "openbsd" ]; then
		check_number_at_least 7.1
	else
		exit 1
	fi
}

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "client-active-hook" ]; then
	check_client_active_hook
else
	show_usage
	exit 1
fi
