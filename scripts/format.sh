#!/bin/sh

# Uses my Emacs formatting style to either format, or check the format of,
# shell scripts within the project.

set -e

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

check_file_format() {
	out=$(mktemp /tmp/authshoe-format-XXXXXXXX.sh)

	differ=
	cat "$1" >>"$out"
	format_file "$out"
	diff -q "$1" "$out" >>/dev/null || {
		differ=1
	}
	if [ -n "$differ" ]; then
		diff -u "$1" "$out"
		rm -f "$out"
		return 1
	fi
	rm -f "$out"
}

list_files() {
	find "$(dirname "$(dirname "$0")")" -name '*.sh' -and -not -path '*/.venv/*'
}

process_files() {
	error=
	for f in $(list_files); do
		$1 "$f"
	done
	if [ -n "$error" ]; then
		return 1
	else
		echo "$1 successful"
	fi
}

if [ "$1" = "check" ]; then
	process_files check_file_format
elif [ "$1" = "shellcheck" ]; then
	process_files shellcheck
else
	process_files format_file
fi
