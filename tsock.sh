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
#
# For the latest version see:
# https://github.com/mshroyer/config/blob/master/cfg.bin/tsock.sh
# or ~mshroyer/cfg.bin/tsock.sh on the sdf.org cluster or MetaArray

VERSION=0.1.0

set -e
set -C  # noclobber for lock file

if [ -f "$HOME/.tsock.conf" ]; then
	. "$HOME/.tsock.conf"
fi

# $UID is not portable
MYUID="$(id -u)"
if [ -z "$TSOCK_TMPDIR" ]; then
	TSOCK_TMPDIR="/tmp"
fi
if [ -z "$TSOCK_DIR" ]; then
	TSOCK_DIR="$TSOCK_TMPDIR/tsock-$MYUID"
fi
SERVERSDIR="$TSOCK_DIR/servers"
TTYSDIR="$TSOCK_DIR/ttys"
LOCKFILE="$TSOCK_DIR/lock"

show_usage() {
cat <<'EOF'
tsock.sh - Wrangle SSH agent sockets for tmux sessions

Usage:
    tsock.sh set-tty-link
    tsock.sh set-server-link [client_tty]
    tsock.sh show-server-link
    tsock.sh version
    tsock.sh help
EOF
}

log() {
	if [ -n "$TSOCK_LOG" ]; then
		echo "$(date +'%Y-%m-%d %H:%M:%S') $1" >>"$TSOCK_LOG"
	fi
	if [ -n "$2" ]; then
		echo "$1" >&2
	fi
}

### Auth socket management ###################################################

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
	echo "/$(echo "$1" | tr + /)"
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

get_pid_uid() {
	ps -o uid -p "$1" | awk 'NR==2 { print $1; }'
}

ensure_dir() {
	if [ ! -d "$1" ]; then
		mkdir -m700 "$1"
	fi
	if [ ! -O "$1" ]; then
		log "expected $1 to be owned by UID $MYUID" 1
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
			log "gc_tty_links: removing $TTYSDIR/$ttylink"
			rm "$TTYSDIR/$ttylink"
		fi
	done
}

get_tty_link_path() {
	echo "$TTYSDIR/$(get_device_filename "$1")"
}

set_tty_link() {
	ensure_dir "$TSOCK_DIR"
	ensure_dir "$TTYSDIR"
	ensure_dir "$SERVERSDIR"

	take_lock

	# Since this will be called infrequently, typically when new SSH
	# clients connect, it's a good place to GC old symlinks.
	gc_tty_links
	gc_server_links

	if [ -n "$SSH_AUTH_SOCK" ] && [ -O "$SSH_AUTH_SOCK" ]; then
		set_symlink "$SSH_AUTH_SOCK" "$(get_tty_link_path $(tty))"
	fi
}

get_active_client_tty() {
	if [ -n "$TMUX" ]; then
		socket=$(echo "$TMUX" | cut -d, -f1)
		tty=$("tmux -S "$socket" display-message -p '#{client_tty}'")
		log "Got active client TTY from $socket: $tty"
		echo tty
	fi
}

get_server_link_path() {
	pid=$(echo "$TMUX" | cut -d, -f2)
	if [ -n "$pid" ]; then
		echo "$SERVERSDIR/$pid"
	fi
}

release_lock() {
	rm -f "$LOCKFILE"
	exit
}

take_lock() {
	n=10
	locked=""
	while [ "$n" -gt "0" ]; do
		if ( echo $$ >"$LOCKFILE" ) 2>>/dev/null; then
			locked=1
			break
		fi
		sleep 0.1
		n="$(expr "$n" - 1)"
		if [ "$(get_pid_uid $(cat "$LOCKFILE"))" != "$MYUID" ]; then
			log "removing stale lockfile $LOCKFILE" t
			rm -f "$LOCKFILE"
		fi
	done

	if [ -z "$locked" ]; then
		log "can't take lockfile $LOCKFILE: locked by PID $(cat "$LOCKFILE")" t
		exit 1
	fi
	trap release_lock INT TERM EXIT
}

set_server_link() {
	serverlink="$(get_server_link_path)"
	if [ -z "$serverlink" ]; then
		return
	fi
	ttylink="$(get_tty_link_path "$1")"

	# This may be called frequently, as a ZSH hook or periodically, so
	# let's optimize the happy path where the link is already set
	# correctly.
	if [ "$(readlink "$serverlink")" = "$ttylink" ]; then
		exit 0
	fi

	log "set_server_link: changing $serverlink -> $ttylink"

	ensure_dir "$TSOCK_DIR"
	ensure_dir "$SERVERSDIR"

	take_lock
	set_symlink "$ttylink" "$serverlink"
}

gc_server_links() {
	for link in $(ls "$SERVERSDIR"); do
		pid_uid="$(get_pid_uid "$link")"
		if [ "$pid_uid" != "$MYUID" ]; then
			log "gc_server_links: removing $SERVERSDIR/$link"
			rm "$SERVERSDIR/$link"
		fi
	done
}

#### Installation ############################################################

TSOCK_SECTION_BEGIN='### TSOCK INSTALLATION BEGIN'
TSOCK_SECTION_END='### TSOCK INSTALLATION END'

# Ensures non-empty files have a trailing newline, otherwise read -r will fail
# to return the last line.
ensure_trailing_newline() {
	if [ ! -s "$1" ]; then
		return
	fi
	code=$(tail -c 1 "$1" | od -An -t u1)
	case "$code" in
		*10*) : ;;
		*) printf '\n' >> "$1" ;;
	esac
}

# Checks whether the file given as an argument contains manual tsock
# configuration--that is, outside of an explicitly marked configuration
# section as created by this script.
has_manual_config() {
	rc_section=head
	while IFS= read -r line; do
		if [ "$line" = "$TSOCK_SECTION_BEGIN" ]; then
			rc_section=installation
		elif [ "$line" = "$TSOCK_SECTION_END" ]; then
			rc_section=tail
		elif [ $rc_section != installation ]; then
			if echo "$line" | grep -Eq 'tsock\.sh[ \t]+(set-tty-link|(set|show)-server-link)'; then
				return
			fi
		fi
	done < "$1"
	false
}

# Creates or replaces the tsock installation section in the file given in $1,
# using the text piped into this function.
set_tsock_section() {
	rc_tempdir=$(mktemp -d "$TSOCK_TMPDIR/tsock-rc-XXXXXXXX")
	rc_section=head
	rc_existing_content=

	if [ ! -e "$1" ]; then
		touch "$1"
	elif [ ! -f "$1" ]; then
		log "Expected $1 to be a file" t
		exit 1
	else
		ensure_trailing_newline "$1"
	fi

	while IFS= read -r line; do
		if [ "$line" = "$TSOCK_SECTION_BEGIN" ]; then
			rc_section=installation
		elif [ "$line" = "$TSOCK_SECTION_END" ]; then
			rc_section=tail
		elif [ $rc_section != installation ]; then
			rc_existing_content=1
			echo "$line" >>"$rc_tempdir/$rc_section"
		fi
	done < "$1"

	touch "$rc_tempdir/installation"
	if [ $rc_section = head ] && [ -n "$rc_existing_content" ]; then
		printf '\n' >>"$rc_tempdir/installation"
	fi
	echo "$TSOCK_SECTION_BEGIN" >>"$rc_tempdir/installation"
	while IFS= read line; do
		echo "$line" >>"$rc_tempdir/installation"
	done
	echo "$TSOCK_SECTION_END" >>"$rc_tempdir/installation"

	touch "$rc_tempdir/head"
	touch "$rc_tempdir/tail"
	cat "$rc_tempdir/head" >|"$1"
	cat "$rc_tempdir/installation" >>"$1"
	cat "$rc_tempdir/tail" >>"$1"

	rm -rf "$rc_tempdir"
}

#### Main ####################################################################

if [ "$1" = "-h" ] || [ "$1" = "help" ]; then
	show_usage
elif [ "$1" = "version" ]; then
	echo "$VERSION"
elif [ "$1" = "set-tty-link" ]; then
	log "$1 $2"
	set_tty_link
elif [ "$1" = "set-server-link" ]; then
	log "$1 $2 $3"
	shift
	if [ -z "$1" ] || [ "$1" = "-" ]; then
		client_tty="$(get_active_client_tty)"
		if [ -n "$client_tty" ]; then
			set_server_link "$client_tty"
		fi
	else
		set_server_link "$1"
	fi
elif [ "$1" = "show-server-link" ]; then
	get_server_link_path
elif [ -n "$TSOCK_TESTONLY_COMMANDS" ]; then
	if [ "$1" = "get-device-filename" ]; then
		get_device_filename "$2"
	elif [ "$1" = "get-filename-device" ]; then
		get_filename_device "$2"
	elif [ "$1" = "set-tsock-section" ]; then
		set_tsock_section "$2"
	elif [ "$1" = "has-manual-config" ]; then
		has_manual_config "$2"
	else
		show_usage
		exit 1
	fi
else
	show_usage
	exit 1
fi
