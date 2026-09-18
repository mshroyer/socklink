#!/bin/sh

# Uses my Emacs formatting style to either format, or check the format of,
# shell scripts within the project.

set -e

PROJECT=$(cd "$(dirname "$0")/.." && pwd)

format_file() {
	emacs -q -nw --batch "$1" --eval '
(progn
  (sh-mode)
  (setq sh-basic-offset 8
        indent-tabs-mode t)
  (indent-region (point-min) (point-max))
  (save-buffer))
' 2>>/dev/null
}

format_check_file() {
	out="$(mktemp /tmp/socklink-format-XXXXXXXX.sh)"

	# shellcheck disable=SC2064
	trap "rm -f $out" EXIT

	differ=
	cat "$1" >>"$out"
	format_file "$out"
	diff -q "$1" "$out" >>/dev/null || {
		differ=1
	}
	if [ -n "$differ" ]; then
		diff -u "$1" "$out"
		return 1
	fi
}

list_files() {
	find "$PROJECT" \( -name '*.sh' -or -name 'lib' \) -and -not -path '*/.venv/*'
}

process_files() {
	batch_mode="$1"
	cmd="$2"

	case "$batch_mode" in
		individually)
			for f in $(list_files); do
				"$cmd" "$f"
			done
			;;

		batched)
			files="$(list_files)"
			echo "$files" | xargs "$cmd"
			;;

		*)
			echo "Unknown batch mode $batch_mode" >&2
			exit 2
			;;
	esac
}

if [ "$1" = "check" ]; then
	process_files individually format_check_file
elif [ "$1" = "shellcheck" ]; then
	process_files batched shellcheck
else
	process_files individually format_file
fi
