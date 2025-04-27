#!/bin/sh

# tmux SSH authentication socket wrangler
#
# Through integration into shell init and tmux hooks, this script maintains a
# tmp directory to maintain a symlink map of our tty device names to the SSH
# authentication sockets associated with them, and another set of symlinks
# mapping tmux session names to those tty symlinks.

set -e

TSOCKDIR="/tmp/tsock-$(id -u)"
SERVERSDIR="$TSOCKDIR/servers"
TTYSDIR="$TSOCKDIR/ttys"
UNAME="$(uname)"

stat_mode() {
	if [ "$UNAME" = "Linux" ]; then
		stat -c '%a' "$1"
	else
		stat -f '%Lp' "$1"
	fi
}

ensure_dir() {
	if [ ! -d $1 ]; then
		mkdir -m700 $1
	fi
	if [ ! -O $1 ]; then
		echo "expected $1 to be owned by $(id -u)" >&2
		exit 1
	fi
	if [ "$(stat_mode $1)" != 700 ]; then
		chmod 700 $1
	fi
}

get_device_filename() {
	echo "$1" | grep -q '^/dev/' || {
		echo "expected path starting with /dev/" >&2
		exit 1
	}
	if echo "$1" | grep -q +; then
		echo "device name $1 containing '+' is unsupported" >&2
		exit 1
	fi
	if echo "$1" | grep -q ' '; then
		echo "device name $1 containing a space is unsupported" >&2
		exit 1
	fi
	echo $1 | cut -c2- | tr / +
}

get_filename_device() {
	echo "/$(echo $1 | tr + /)"
}

set_symlink() {
	if [ -e "$2" ]; then
		rm "$2"
	fi
	ln -s "$1" "$2"
}

get_tty_link_path() {
	echo "$TTYSDIR/$(get_device_filename $1)"
}

set_tty_link() {
	if [ ! -z "$SSH_AUTH_SOCK" ] && [ -O "$SSH_AUTH_SOCK" ]; then
		set_symlink $SSH_AUTH_SOCK "$(get_tty_link_path $(tty))"
	fi
}

# Clean up any of the tty links that no longer both refer to an existing tty
# owned by us, and point to a still-present authentication socket.
gc_tty_links() {
	cd $TTYSDIR
	for ttylink in *; do
		if [ ! -O "$(get_filename_device $ttylink)" ] \
			   || [ ! -O "$(readlink $ttylink)" ]; then
			rm $ttylink
		fi
	done
}

show_usage() {
cat <<'EOF'
tsock.sh - Wrangle SSH agent sockets for tmux sessions

Usage:
    tsock.sh set-tty-link
    tsock.sh show-server-link
    tsock.sh help
EOF
}

ensure_dirs() {
	ensure_dir "$TSOCKDIR"
	ensure_dir "$SERVERSDIR"
	ensure_dir "$TTYSDIR"
}

get_active_client_tty() {
	tmux list-clients -F '#{client_activity} #{client_tty}' \
		| sort -r \
		| awk 'NR==1 { print $2; }'
}

get_server_link_path() {
	echo "$SERVERSDIR/$(tmux list-sessions -F '#{pid}' | head -n1)"
}

set_server_link() {
	set_symlink "$(get_tty_link_path $(get_active_client_tty))" \
		    "$(get_server_link_path)"
}

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "set-tty-link" ]; then
	ensure_dirs
	gc_tty_links
	set_tty_link
elif [ "$1" = "set-server-link" ]; then
	set_server_link
elif [ "$1" = "show-server-link" ]; then
	get_server_link_path
else
	show_usage
	exit 1
fi
