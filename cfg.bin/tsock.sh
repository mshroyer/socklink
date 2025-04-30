#!/bin/sh

# tmux SSH authentication socket wrangler
#
# This maintains a two-level symlink map of a user's tmux server PIDs to the
# SSH_AUTH_SOCKs they opened their current clients with.  The first level maps
# the server PID to a filename representing a client tty/pty; the second level
# maps that tty filename to the original auth socket.  The second level may be
# missing if, for example, the client logged in without SSH agent forwarding.
# This is intentional and seems to result in desired behavior from OpenSSH.
#
# The purpose is that when hooked up correctly, this script will make SSH
# authentication requests "just work", in that they'll be directed to the
# user's currently active tmux client--even if the user is connected
# simultaneously from multiple clients.  This behavior is helpful when using a
# hardware authenticator at your physical workstation, such as a YubiKey with
# touch enabled.
#
# (Ideally we might have per-session accounting of the active client and then
# per-pane mappings to original SSH_AUTH_SOCKs, allowing for the panes to be
# moved between sessions.  But that's a heck of a lot more bookkeeping!)
#
# set-tty-link saves the client tty -> auth socket link.  This should be
# called when starting a non-tmux interactive shell, before it starts a tmux
# client.
#
# set-server-link saves the server PID -> client tty link.  This should be
# called with the new client's tty when the active client changes.  If called
# without an argument, it will look up the most-recent client automatically.
#
# show-server-link gets the path to the server's PID link.  This should be
# used to set SSH_AUTH_SOCK in new shells created within tmux.
#
# Works on Debian 12, AlmaLinux 9, OpenBSD 7.6, FreeBSD 14.2, NetBSD 9.3, and
# macOS Sequoia 15.4.

set -e

LOGFILE=

# $UID is not portable
MYUID="$(id -u)"
TSOCKDIR="/tmp/tsock-$MYUID"
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
	if [ -n "$LOGFILE" ]; then
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
	if [ "$(stat_mode "$1")" != 700 ]; then
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
	for ttylink in $(ls "$TTYSDIR"); do
		if [ ! -O "$(get_filename_device "$ttylink")" ] \
			   || [ ! -O "$(readlink "$TTYSDIR/$ttylink")" ]; then
			rm "$TTYSDIR/$ttylink"
		fi
	done
}

get_tty_link_path() {
	echo "$TTYSDIR/$(get_device_filename "$1")"
}

set_tty_link() {
	ensure_dir "$TSOCKDIR"
	ensure_dir "$TTYSDIR"
	ensure_dir "$SERVERSDIR"

	# Since this will be called infrequently, typically when new SSH
	# clients connect, it's a good place to GC old symlinks.
	gc_tty_links
	gc_server_links

	if [ -n "$SSH_AUTH_SOCK" ] && [ -O "$SSH_AUTH_SOCK" ]; then
		set_symlink "$SSH_AUTH_SOCK" "$(get_tty_link_path $(tty))"
	fi
}

get_active_client_tty() {
	tmux list-clients -F '#{client_activity} #{client_tty}' \
		| sort -r \
		| awk 'NR==1 { print $2; }'

	# In theory `tmux run-shell` should tell us what we need, but on
	# Raspbian it takes over the entire tmux session in view mode and I
	# don't know why:

	#tmux run-shell 'echo #{client_tty}'
}

get_server_link_path() {
	echo "$SERVERSDIR/$(tmux list-sessions -F '#{pid}' | head -n1)"
}

set_server_link() {
	ttylink="$(get_tty_link_path "$1")"
	serverlink="$(get_server_link_path)"

	# This may be called frequently, as a ZSH hook or periodically, so
	# let's optimize the happy path where the link is already set
	# correctly.
	if [ -L "$serverlink" ] && [ "$(readlink "$serverlink")" = "$ttylink" ]; then
		exit 0
	fi

	ensure_dir "$TSOCKDIR"
	ensure_dir "$SERVERSDIR"
	set_symlink "$ttylink" "$serverlink"
}

get_pid_uid() {
	ps -o uid -p "$1" | awk 'NR==2 { print $1; }'
}

gc_server_links() {
	for link in $(ls "$SERVERSDIR"); do
		pid_uid="$(get_pid_uid "$link")"
		if [ -z "$pid_uid" ] || [ "$pid_uid" != "$MYUID" ]; then
			rm "$SERVERSDIR/$link"
		fi
	done
}

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "set-tty-link" ]; then
	log "$@"
	set_tty_link
elif [ "$1" = "set-server-link" ]; then
	log "$@"
	shift
	if [ -n "$1" ]; then
		set_server_link "$1"
	else
		set_server_link "$(get_active_client_tty)"
	fi
elif [ "$1" = "show-server-link" ]; then
	get_server_link_path
else
	show_usage
	exit 1
fi
