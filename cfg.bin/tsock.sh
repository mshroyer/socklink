#!/bin/sh

# tmux SSH authentication socket wrangler
#
# Through integration into shell init and tmux hooks, this script maintains a
# tmp directory to maintain a symlink map of our tty device names to the SSH
# authentication sockets associated with them, and another set of symlinks
# mapping tmux session names to those tty symlinks.

set -e

LOGFILE=

TSOCKDIR="/tmp/tsock-$(id -u)"
SERVERSDIR="$TSOCKDIR/servers"
TTYSDIR="$TSOCKDIR/ttys"

show_usage() {
cat <<'EOF'
tsock.sh - Wrangle SSH agent sockets for tmux sessions

Usage:
    tsock.sh set-tty-link
    tsock.sh set-server-link [client_tty]
    tsock.sh show-server-link
    tsock.sh help
EOF
}

log() {
	if [ ! -z "$LOGFILE" ]; then
		echo "$(date +'%Y-%m-%d %H:%M:%S') $1" >>"$LOGFILE"
	fi
}

# Converts absolute path to a device node into a string that can be used as a
# filename: /dev/pts/98 -> dev+pts+98
get_device_filename() {
	echo "$1" | grep -q '^/dev/' || {
		echo "expected path starting with /dev/" >&2
		exit 1
	}
	if echo "$1" | grep -q '[+ ]'; then
		echo "device name $1 containing '+' or space is unsupported" >&2
		exit 1
	fi
	echo $1 | cut -c2- | tr / +
}

# Reverses get_device_filename
get_filename_device() {
	echo "/$(echo $1 | tr + /)"
}

UNAME=
stat_mode() {
	if [ -z "$UNAME" ]; then
		UNAME="$(uname)"
	fi
	if [ "$UNAME" = "Linux" ]; then
		stat -c '%a' "$1"
	else
		stat -f '%Lp' "$1"
	fi
}

ensure_dir() {
	if [ ! -d "$1" ]; then
		mkdir -m700 "$1"
	fi
	if [ ! -O "$1" ]; then
		echo "expected $1 to be owned by $(id -u)" >&2
		exit 1
	fi
	if [ "$(stat_mode $1)" != 700 ]; then
		chmod 700 "$1"
	fi
}

set_symlink() {
	if [ -L "$2" ] || [ -e "$2" ]; then
		rm "$2"
	fi
	ln -s "$1" "$2"
}

# Clean up any of the tty links that no longer both refer to an existing tty
# owned by us, and point to a still-present authentication socket.
gc_tty_links() {
	for ttylink in $(ls $TTYSDIR); do
		if [ ! -O "$(get_filename_device $ttylink)" ] \
			   || [ ! -O "$(readlink $TTYSDIR/$ttylink)" ]; then
			rm "$TTYSDIR/$ttylink"
		fi
	done
}

get_tty_link_path() {
	echo "$TTYSDIR/$(get_device_filename $1)"
}

set_tty_link() {
	ensure_dir "$TSOCKDIR"
	ensure_dir "$TTYSDIR"

	# Since this will be called infrequently, typically when new SSH
	# clients connect, it's a good place to GC old symlinks.
	gc_tty_links

	if [ ! -z "$SSH_AUTH_SOCK" ] && [ -O "$SSH_AUTH_SOCK" ]; then
		set_symlink "$SSH_AUTH_SOCK" "$(get_tty_link_path $(tty))"
	fi
}

get_active_client_tty() {
	# tmux list-clients -F '#{client_activity} #{client_tty}' \
	# 	| sort -r \
	# 	| awk 'NR==1 { print $2; }'
	tmux run-shell 'echo #{client_tty}'
}

get_server_link_path() {
	echo "$SERVERSDIR/$(tmux list-sessions -F '#{pid}' | head -n1)"
}

set_server_link() {
	ttylink="$(get_tty_link_path $1)"
	serverlink="$(get_server_link_path)"

	# This may be called frequently, as a ZSH hook or periodically, so
	# let's optimize the happy path where the link is already set
	# correctly.
	if [ -L $serverlink ] && [ "$(readlink $serverlink)" = "$ttylink" ]; then
		return
	fi

	ensure_dir "$TSOCKDIR"
	ensure_dir "$SERVERSDIR"
	set_symlink "$ttylink" "$serverlink"
}

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "set-tty-link" ]; then
	log "$@"
	set_tty_link
elif [ "$1" = "set-server-link" ]; then
	log "$@"
	shift
	if [ -z "$1" ]; then
		set_server_link "$(get_active_client_tty)"
	else
		set_server_link "$1"
	fi
elif [ "$1" = "show-server-link" ]; then
	get_server_link_path
else
	show_usage
	exit 1
fi
