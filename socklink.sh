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
# https://github.com/mshroyer/socklink/blob/main/socklink.sh
#
# Users of sdf.org can also find the latest release at ~mshroyer/socklink.sh
# on either the regular cluster or MetaArray.

VERSION="0.3.0-dev"

set -eC  # noclobber for lock file

CONFFILE="$HOME/.socklink.conf"
if [ -f "$CONFFILE" ]; then
	# shellcheck disable=SC1090
	. "$CONFFILE"
fi

# $UID is not totally portable
MYUID="$(id -u)"
if [ -z "$SOCKLINK_TMPDIR" ]; then
	SOCKLINK_TMPDIR="/tmp"
fi
if [ -z "$SOCKLINK_DIR" ]; then
	SOCKLINK_DIR="$SOCKLINK_TMPDIR/socklink-$MYUID"
fi
SERVERSDIR="$SOCKLINK_DIR/servers"
TTYSDIR="$SOCKLINK_DIR/ttys"
LOCKFILE="$SOCKLINK_DIR/lock"

show_usage() {
	cat <<'EOF'
socklink.sh - Wrangle SSH agent sockets for tmux sessions

Usage:
    socklink.sh set-tty-link
    socklink.sh set-server-link [client_tty]
    socklink.sh set-server-link-by-name client_name
    socklink.sh set-tmux-env
    socklink.sh show-server-link
    socklink.sh setup
    socklink.sh version
    socklink.sh help
EOF
}

log() {
	if [ -n "$SOCKLINK_LOG" ]; then
		echo "$(date +'%Y-%m-%d %H:%M:%S') $1" >>"$SOCKLINK_LOG"
	fi
	if [ -n "$2" ]; then
		echo "$1" >&2
	fi
}

### Auth socket management ###################################################

# Reversably maps an absolute path of a device node to a string that can be
# used as a filename: /dev/pts/98 -> dev+pts+98
get_device_filename() {
	echo "$1" | grep -q '^/dev/' || {
		echo "expected path starting with /dev/" >&2
		exit 1
	}
	if echo "$1" | grep -q '[+ ]'; then
		echo "device name $1 containing '+' or space is unsupported" >&2
		exit 1
	fi
	echo "$1" | cut -c2- | tr / +
}

# Reverses get_device_filename
get_filename_device() {
	echo "/$(echo "$1" | tr + /)"
}

stat_mode() {
	case "$(uname)" in
		*BSD|Darwin)
			stat -f '%Lp' "$1"
			;;

		*)
			stat -c '%a' "$1"
			;;
	esac
}

BUSYBOX_PS=
get_pid_uid() {
	if [ -z "$BUSYBOX_PS" ] && [ "$(uname)" = "Linux" ]; then
		ps="$(which ps)"
		if [ -L "$ps" ] && [ "$(basename "$(readlink "$ps")")" = "busybox" ]; then
			BUSYBOX_PS=1
		fi
	fi

	if [ -n "$BUSYBOX_PS" ]; then
		# The ps invocation below also works for most Linux
		# distributions, however Alpine Linux's busybox ps
		# implementation doesn't support -o uid.
		awk '/^Uid:/ { print $2; }' "/proc/$1/status" 2>>/dev/null || echo ""
	else
		ps -o uid -p "$1" | awk 'NR==2 { print $1; }'
	fi
}

ensure_dir() {
	if [ ! -d "$1" ]; then
		mkdir -m700 "$1"
	fi
	if [ ! -O "$1" ]; then
		log "expected $1 to be owned by UID $MYUID" 1
		exit 1
	fi
	mode="$(stat_mode "$1")"
	if [ "$mode" != 700 ]; then
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
	for tty_link in "$TTYSDIR"/*; do
		[ -L "$tty_link" ] || [ -e "$tty_link" ] || continue

		tty_device="$(get_filename_device "$(basename "$tty_link")")"
		if [ ! -O "$tty_device" ]; then
			log "gc_tty_links: removing $tty_link: $tty_device missing or not owned"
			rm -f "$tty_link"
			continue
		fi
		tty_sock="$(readlink "$tty_link")"
		if [ ! -O "$tty_sock" ]; then
			log "gc_tty_links: removing $tty_link: $tty_sock missing or not owned"
			rm -f "$tty_link"
		fi
	done
}

get_tty_link_path() {
	echo "$TTYSDIR/$(get_device_filename "$1")"
}

# Sets a link to a non-tmux shell's original $SSH_AUTH_SOCK keyed by the name
# of its tty.
set_tty_link() {
	ensure_dir "$SOCKLINK_DIR"
	ensure_dir "$TTYSDIR"
	ensure_dir "$SERVERSDIR"

	take_lock

	# Since this will be called infrequently, typically when new SSH
	# clients connect, it's a good place to GC old symlinks.
	gc_tty_links
	gc_server_links

	if [ -n "$SSH_AUTH_SOCK" ] && [ -O "$SSH_AUTH_SOCK" ]; then
		set_symlink "$SSH_AUTH_SOCK" "$(get_tty_link_path "$(tty)")"
	fi
}

get_active_client_tty() {
	if [ -n "$TMUX" ]; then
		socket=$(echo "$TMUX" | cut -d, -f1)
		tty=$(tmux -S "$socket" display-message -p '#{client_tty}')
		log "get_active_client_tty $socket: $tty"
		echo "$tty"
	fi
}

get_server_link_path() {
	pid="$(echo "$TMUX" | cut -d, -f2)"
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
		n=$(("$n" - 1))
		uid="$(get_pid_uid "$(cat "$LOCKFILE")")"
		if [ "$uid" != "$MYUID" ]; then
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

# Links the server's PID to the tty name of its currently active client.
#
# If the optional client_tty parameter is not given, looks up the currently
# actively client by tmux's own reckoning.
set_server_link() {
	log "set_server_link: cause = '$cause_flag', client_tty = '$client_tty'"

	client_tty="$1"
	if [ -z "$client_tty" ] || [ "$client_tty" = "-" ]; then
		client_tty="$(get_active_client_tty)"
	fi

	serverlink="$(get_server_link_path)"
	if [ -z "$serverlink" ]; then
		log "set_server_link: server link is unset" t
		exit 1
	fi
	tty_link="$(get_tty_link_path "$client_tty")"

	# This may be called frequently, as a ZSH hook or periodically, so
	# let's optimize the happy path where the link is already set
	# correctly.
	target="$(readlink "$serverlink")" || target=
	if [ "$target" = "$tty_link" ]; then
		exit 0
	fi

	log "set_server_link: changing $serverlink -> $tty_link"

	ensure_dir "$SOCKLINK_DIR"
	ensure_dir "$SERVERSDIR"

	take_lock
	set_symlink "$tty_link" "$serverlink"
}

# Links the server's PID to the tty based on the tmux client name instead of
# the tty device path.  This allows us to use the client-active hook's
# #{hook_client} variable instead of #{client_tty}, the latter of which can
# race with the hook's execution.
#
# In practice the client name seems to be equal to the tty device in all
# scenarios I've been able to reproduce, so this lookup may not be strictly
# necessary.
set_server_link_by_name() {
	client_name="$1"
	if [ -z "$client_name" ]; then
		log "set_server_link_by_name: client_name not given" t
		exit 1
	fi

	client_tty="$(get_named_client_tty "$client_name")"
	if [ -n "$client_tty" ]; then
		set_server_link "$client_tty"
	fi
}

# Sets SSH_AUTH_SOCK in the server's global tmux environment.
#
# This may be useful for user tmux hooks that do things with SSH.  It isn't
# sufficient to skip also setting SSH_AUTH_SOCK within in-tmux shells' init,
# however.
set_tmux_env() {
	if [ -z "$TMUX" ]; then
		log "set_tmux_env: \$TMUX not set, aborting" t
		exit 1
	fi
	server_link="$(get_server_link_path)"
	tmux set-environment -g SSH_AUTH_SOCK "$server_link"
}

# Allow for setting the server link with a client identified by name instead
# of by tty.  This is useful because tmux currently has a #{hook_client}
# format variable that resolves to the triggering client name, but no
# #{hook_client_tty}.
get_named_client_tty() {
	for client in $(tmux list-clients -F '#{client_name}:#{client_tty}'); do
		cname=$(echo "$client" | cut -d: -f1)
		ctty=$(echo "$client" | cut -d: -f2)
		if [ "$cname" = "$1" ]; then
			echo "$ctty"
			return
		fi
	done
}

gc_server_links() {
	for link in "$SERVERSDIR"/*; do
		[ -L "$link" ] || [ -e "$link" ] || continue

		pid_uid="$(get_pid_uid "$(basename "$link")")"
		if [ "$pid_uid" != "$MYUID" ]; then
			log "gc_server_links: removing $link"
			rm -f "$link"
		fi
	done
}

#### Installation ############################################################

SOCKLINK_SECTION_BEGIN='### SOCKLINK INSTALLATION BEGIN'
SOCKLINK_SECTION_END='### SOCKLINK INSTALLATION END'

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

# Checks whether the file given as an argument contains manual socklink
# configuration--that is, outside of an explicitly marked configuration
# section as created by this script.
has_manual_config() {
	rc_section="head"
	while IFS= read -r line; do
		if [ "$line" = "$SOCKLINK_SECTION_BEGIN" ]; then
			rc_section=installation
		elif [ "$line" = "$SOCKLINK_SECTION_END" ]; then
			rc_section="tail"
		elif [ $rc_section != installation ]; then
			if echo "$line" | grep -Eq 'socklink\.sh[[:space:]]+(set-tty-link|(set|show)-server-link)'; then
				return
			fi
		fi
	done < "$1"
	false
}

# Creates or replaces the socklink installation section in the file given in $1,
# using the text piped into this function.
set_socklink_section() {
	rc_tempdir=$(mktemp -d "$SOCKLINK_TMPDIR/socklink-rc-XXXXXXXX")
	rc_section="head"
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
		if [ "$line" = "$SOCKLINK_SECTION_BEGIN" ]; then
			rc_section=installation
		elif [ "$line" = "$SOCKLINK_SECTION_END" ]; then
			rc_section="tail"
		elif [ $rc_section != installation ]; then
			rc_existing_content=1
			echo "$line" >>"$rc_tempdir/$rc_section"
		fi
	done < "$1"

	touch "$rc_tempdir/installation"
	if [ $rc_section = head ] && [ -n "$rc_existing_content" ]; then
		printf '\n' >>"$rc_tempdir/installation"
	fi
	echo "$SOCKLINK_SECTION_BEGIN" >>"$rc_tempdir/installation"
	while IFS= read -r line; do
		echo "$line" >>"$rc_tempdir/installation"
	done
	echo "$SOCKLINK_SECTION_END" >>"$rc_tempdir/installation"

	touch "$rc_tempdir/head"
	touch "$rc_tempdir/tail"
	cat "$rc_tempdir/head" >|"$1"
	cat "$rc_tempdir/installation" >>"$1"
	cat "$rc_tempdir/tail" >>"$1"

	rm -rf "$rc_tempdir"
}

get_script() {
	if which realpath >>/dev/null; then
		script="$(realpath "$0")"
	else
		script="$0"
	fi
	if echo "$script" | grep -q "^$HOME/"; then
		script="\$HOME${script#"$HOME"}"
	fi
	echo "$script"
}

setup_tmux_conf() {
	script="$(get_script)"

	set_socklink_section "$HOME/.tmux.conf" <<EOF
if-shell -b '$script has-client-active-hook' {
	set-hook -ga client-active 'run-shell "$script -c client-active set-server-link-by-name #{hook_client}"'
}
set-hook -ga client-attached 'run-shell "$script -c client-attached set-server-link #{client_tty}"'
set-hook -ga session-created 'run-shell "$script -c session-created set-server-link #{client_tty}"'
set-hook -ga session-created 'run-shell "$script -c session-created set-tmux-env"'
EOF
}

setup_bashrc() {
	set_socklink_section "$HOME/.bashrc" <<EOF
if [[ \$- == *i* ]]; then
	if [ -z "\$TMUX" ]; then
		$script set-tty-link -c shell-init
	else
		export SSH_AUTH_SOCK="\$($script show-server-link)"
	fi
fi
EOF
}

setup_zshrc() {
	set_socklink_section "$HOME/.zshrc" <<EOF
if [[ -o interactive ]]; then
	if [ -z "\$TMUX" ]; then
		$script set-tty-link -c shell-init
	else
		export SSH_AUTH_SOCK="\$($script show-server-link)"
	fi
fi
EOF
}

setup() {
	setup_tmux_conf
	setup_bashrc
	setup_zshrc
}

#### Feature checks ##########################################################

check_number_at_least() {
	awk -v n="$2" -v c="$1" 'BEGIN{ exit !(c+0 <= n+0) }'
}

has_client_active_hook() {
	verstr="$1"
	if [ -z "$verstr" ]; then
		verstr="$(tmux -V)"
	fi
	prefix="$(echo "$verstr" | sed -E 's/^tmux ((.*)-)?([0-9]+\.[0-9]+)(.*)/\2/')"
	number="$(echo "$verstr" | sed -E 's/^tmux ((.*)-)?([0-9]+\.[0-9]+)(.*)/\3/')"

	if [ "$prefix" = "openbsd" ]; then
		check_number_at_least 7.1 "$number"
	else
		check_number_at_least 3.3 "$number"
	fi
}

#### Main ####################################################################

cause_flag=
help_flag=
version_flag=
while getopts c:hV flag
do
	case "$flag" in
		c)
			cause_flag="$OPTARG"
			;;
		h)
			help_flag=1
			;;
		V)
			version_flag=1
			;;
		*)
			log "Unknown flag: $flag" t
			exit 1
			;;
	esac
done
shift $((OPTIND - 1))

if [ -n "$help_flag" ] || [ "$1" = "help" ]; then
	show_usage
elif [ -n "$version_flag" ]; then
	echo "$VERSION"
elif [ "$1" = "set-tty-link" ]; then
	log "$@"
	set_tty_link
elif [ "$1" = "set-server-link" ]; then
	log "$@"
	shift
	set_server_link "$@"
elif [ "$1" = "set-server-link-by-name" ]; then
	log "$@"
	shift
	set_server_link_by_name "$@"
elif [ "$1" = "show-server-link" ]; then
	get_server_link_path
elif [ "$1" = "set-tmux-env" ]; then
	set_tmux_env
elif [ "$1" = "has-client-active-hook" ]; then
	has_client_active_hook "$2"
elif [ "$1" = "setup" ]; then
	log "$@"
	setup
elif [ -n "$SOCKLINK_TESTONLY_COMMANDS" ]; then
	if [ "$1" = "get-device-filename" ]; then
		get_device_filename "$2"
	elif [ "$1" = "get-filename-device" ]; then
		get_filename_device "$2"
	elif [ "$1" = "set-socklink-section" ]; then
		set_socklink_section "$2"
	elif [ "$1" = "has-manual-config" ]; then
		has_manual_config "$2"
	elif [ "$1" = "stat-mode" ]; then
		stat_mode "$2"
	elif [ "$1" = "get-pid-uid" ]; then
		get_pid_uid "$2"
	else
		show_usage
		exit 1
	fi
else
	show_usage
	exit 1
fi
